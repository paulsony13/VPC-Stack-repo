import boto3
import json
import sys
import botocore
import time
import os




REGION = 'us-east-1'
CHANGE_SET_NAME = 'deploy-commit-'
STACK_NAME = 'VPC-Stack'
SNS_TOPIC = 'arn:aws:sns:us-east-1:631145538984:SendCINotification'
PARAMS_FILE_UE1 = 'vpc-parameters-ue1.json'
PARAMS_FILE_UE2 = 'vpc-parameters-ue2.json'
TEMPLATE_BODY_FILE = 'vpc.json'
COMMIT =  'fasjjtksdloirnx'
COMMIT_ID = COMMIT[:5]
CF_ROLE_ARN = 'arn:aws:iam::631145538984:role/CF-Access'
filename = 'changeset.json'
SF_ARN='arn:aws:states:us-east-1:631145538984:stateMachine:HumanApprovalLambdaStateMachine-VhajMy09OQvt'


def auth(REGION):
    client = boto3.client('cloudformation', region_name=REGION)
    return client


def describe_stack(stack, region):

    response = auth(region).describe_stacks(
        StackName=stack
    )
    stack_status = response['Stacks'][0]['StackStatus']
    if (stack_status != "UPDATE_COMPLETE" ) and  (stack_status != "CREATE_COMPLETE" ) :
        print("Stack Update/Create Failed")
        print(response['Stacks'][0]['StackStatus'])
        print(response['Stacks'][0]['StackStatusReason'])
        exit(1)
    else:
        print("Update Completed !")


def execute_stack_update(region):
    print("Executing Change Set is region: " + region)
    client = boto3.client('cloudformation', region_name=region)
    try:
        response = client.execute_change_set(
            ChangeSetName=CHANGE_SET_NAME+COMMIT_ID,
            StackName=STACK_NAME
        )
        print("Stack Update in Progress...")
        try:
            waiter = client.get_waiter('stack_update_complete')
            waiter.wait(StackName=STACK_NAME)
            describe_stack(STACK_NAME, region)
        except botocore.exceptions.WaiterError as ex:
            describe_stack(STACK_NAME, region)

    except botocore.exceptions.ClientError as ex:
        error_message = ex.response['Error']['Message']
        print(error_message)

        response = client.describe_change_set(
            ChangeSetName=CHANGE_SET_NAME + COMMIT_ID,
            StackName=STACK_NAME
        )
        print(response['StatusReason'])
        if response['StatusReason'] == "The submitted information didn't contain changes. Submit different information to create a change set.":
            response = client.delete_change_set(
                ChangeSetName=CHANGE_SET_NAME + COMMIT_ID,
                StackName=STACK_NAME
            )
            print(CHANGE_SET_NAME + COMMIT_ID+" ChangeSet Deleted !")


def create_stack(params, region):
    cf_template = open(TEMPLATE_BODY_FILE).read()
    try:
        response = auth(region).create_stack(
            StackName=STACK_NAME,
            TemplateBody=cf_template,
            Parameters=params,
            Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND'],
            RoleARN=CF_ROLE_ARN
        )
        print("Provisioning new Stack in "+region+".....")
        waiter = auth(region).get_waiter('stack_create_complete')
        waiter.wait(StackName=STACK_NAME)
        describe_stack(STACK_NAME, region)
        return 'new-stack'

    except botocore.exceptions.ClientError as ex:
        error_message = ex.response['Error']['Message']

        stack_exists = "Stack ["+STACK_NAME+"] already exists"
        if error_message == stack_exists:
            return 'stack-exists'


def read_parameters_json(PARAMS_FILE):
    file = open(PARAMS_FILE)
    parameter = json.load(file)
    parameter = parameter['Parameters']
    params_list = []
    param = {}
    for key, value in parameter.items():
        param['ParameterKey'] = key
        param['ParameterValue'] = value
        params_list.append(param.copy())
    return params_list


def create_change_set(params, region):
    cf_template = open(TEMPLATE_BODY_FILE).read()
    try:
        response = auth(region).create_change_set(
            StackName=STACK_NAME,
            ChangeSetName=CHANGE_SET_NAME+COMMIT_ID,
            IncludeNestedStacks=True,
            TemplateBody=cf_template,
            Parameters=params,
            Capabilities=['CAPABILITY_IAM','CAPABILITY_NAMED_IAM','CAPABILITY_AUTO_EXPAND'],
            RoleARN=CF_ROLE_ARN
        )

        return "change-set-created"
    except botocore.exceptions.ClientError as ex:
        error_message = ex.response['Error']['Message']
        print(error_message)
        return error_message


def validate_change_set(region):
    change_set = get_change_set(region)
    if not change_set:
        #print("no-cahnges")
        return 'no-changes'
    else:
        print(json.dumps(change_set, indent=4))
        return change_set



def get_change_set(region):
    try:
        waiter = auth(region).get_waiter('change_set_create_complete')
        waiter.wait(
            ChangeSetName=CHANGE_SET_NAME+COMMIT_ID,
            StackName=STACK_NAME,
        )
    except botocore.exceptions.WaiterError as ex:
        pass

    response = auth(region).describe_change_set(
        ChangeSetName=CHANGE_SET_NAME+COMMIT_ID,
        StackName=STACK_NAME
    )

    changes_list = response['Changes']
    if not changes_list:
        print("No Changes found in Template/Parameter, Stack is Up-to-Date")
        return None
    else:
        change_set_list = convert_data(changes_list)
        return change_set_list


def convert_data(data):
    new_data = []
    for i, item in enumerate(data):
        new_item = {
            "SL": i + 1,
            "Action": item["ResourceChange"]["Action"],
            "PhysicalResourceId": item["ResourceChange"]["PhysicalResourceId"],
            "Replacement": item["ResourceChange"]["Replacement"],
            "LogicalResourceId": item["ResourceChange"]["LogicalResourceId"]
        }
        new_data.append(new_item)
    return new_data


def stack_exists(response, region, parameters):
    if response == "stack-exists":
        print("Stack ["+STACK_NAME+"] already exists in " +region)
        print("Discovering new Changes, creating ChangeSet")
        change_set_response = create_change_set(parameters, region)
        if change_set_response == "change-set-created":
            validate_change_set_response = validate_change_set(region)
            ch_set = json.dumps(validate_change_set_response)
            #print(ch_set)
            if validate_change_set_response == "no-changes":
                #print("running no change block")
                #exit(0)
                ch_set = ""
                return ch_set
    return ch_set



def approval(change_set):
    # Create a step functions client
    client = boto3.client('stepfunctions', region_name='us-east-1')
    #Start the execution
    print(json.dumps(change_set, indent=4))
    response=client.start_execution(
        stateMachineArn=SF_ARN,
        input=change_set
    )
    execution_arn = response['executionArn']
    while True:
        response = client.describe_execution(
            executionArn=execution_arn
        )
        if response['status'] == 'SUCCEEDED':
            break
        elif response['status'] == 'FAILED':
            print("Approval Workflow Failed !, Exiting")
            exit(1)
        time.sleep(5)
    response = client.get_execution_history(executionArn=execution_arn)
    for event in response['events']:
        if event['type'] == 'ExecutionSucceeded':
            sf_response = event['executionSucceededEventDetails']['output']


    return sf_response


def update_stack(region, PARAMS_FILE):
    parameters = read_parameters_json(PARAMS_FILE)
    create_stack_response = create_stack(parameters, region)
    #print(create_stack_response)
    if create_stack_response != 'new-stack':
        #print(create_stack_response)
        change_set = stack_exists(create_stack_response, region, parameters)
        if change_set:
            return change_set
        else:
            return None
    else:
        print("Created Stack for first time, so no change sets to approve")
        return "initialstack"


def delete_change_set(region):
    print("Stack Update Rejected or no Changes to apply in region "+region+", Deleting the current change Set created !")
    try:
        response = auth(region).delete_change_set(
            ChangeSetName=CHANGE_SET_NAME + COMMIT_ID,
            StackName=STACK_NAME
        )
        print(CHANGE_SET_NAME + COMMIT_ID + " ChangeSet Deleted !")
    except botocore.exceptions.ClientError as ex:
        error_message = ex.response['Error']['Message']
        print(error_message)

def change_set_null_checker(region, change_set):
    if not change_set:
        print("Change set in region "+region+" is empty")
        #delete_change_set(region)


change_set = {}
change_set_ue1 = update_stack('us-east-1', PARAMS_FILE_UE1)
print("++++++++++++++++++++++++++++++++++++++++++++++++++++")
change_set_ue2 = update_stack('us-east-2', PARAMS_FILE_UE2)
print("++++++++++++++++++++++++++++++++++++++++++++++++++++")
if change_set_ue1 == 'initialstack':
    #print("Initial")
    pass
else:
    change_set['us-east-1'] = change_set_ue1
    change_set_null_checker('us-east-1', change_set_ue1)
if change_set_ue2 == 'initialstack':
    #print("Initial")
    pass
else:
    change_set['us-east-2'] = change_set_ue2
    change_set_null_checker('us-east-2', change_set_ue2)

# print(change_set_ue1)
# print(change_set_ue2)

if change_set_ue1 is None and change_set_ue2 is None:
    print("No Changes to Stacks")

elif change_set_ue1 or change_set_ue2  != 'initialstack':
    response_approval = json.loads(approval(json.dumps(change_set)))
    print(response_approval)
    print("Executing Change Set")
    if response_approval['Status'] == 'Approved' and response_approval['Region'] == 'ue1':
        execute_stack_update('us-east-1')
        #delete_change_set('us-east-2')
    elif response_approval['Status'] == 'Approved' and response_approval['Region'] == 'ue2':
        execute_stack_update('us-east-2')
        #delete_change_set('us-east-1')
    elif response_approval['Status'] == 'Approved' and response_approval['Region'] == 'both':
        execute_stack_update('us-east-1')
        execute_stack_update('us-east-2')
    elif response_approval['Status'] == 'Rejected' and response_approval['Region'] == 'both':
        pass
        #delete_change_set('us-east-1')
        #delete_change_set('us-east-2')




