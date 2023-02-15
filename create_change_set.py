import boto3
import json
import sys
import botocore
import time
import os




REGION = 'us-east-1'
CHANGE_SET_NAME = 'deploy-commit-'
STACK_NAME = 'IAM-Stack'
SNS_TOPIC = 'arn:aws:sns:us-east-1:631145538984:SendCINotification'
PARAMS_FILE_UE1 = 'params-ue1.json'
PARAMS_FILE_UE2 = 'params-ue2.json'
TEMPLATE_BODY_FILE = 'iam-cft.json'
COMMIT =  'fasjjtksdloirnx'
COMMIT_ID = COMMIT[:5]
CF_ROLE_ARN = 'arn:aws:iam::631145538984:role/CF-Access'
filename = 'changeset.json'
SF_ARN='arn:aws:states:us-east-1:631145538984:stateMachine:HumanApprovalLambdaStateMachine-VhajMy09OQvt'





client = boto3.client('cloudformation', region_name=REGION)


def describe_stack(stack):

    response = client.describe_stacks(
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


def get_change_set(region):
    client = boto3.client('cloudformation', region_name=region)
    try:
        waiter = client.get_waiter('change_set_create_complete')
        waiter.wait(
            ChangeSetName=CHANGE_SET_NAME+COMMIT_ID,
            StackName=STACK_NAME,
        )
    except botocore.exceptions.WaiterError as ex:
        pass

    response = client.describe_change_set(
        ChangeSetName=CHANGE_SET_NAME+COMMIT_ID,
        StackName=STACK_NAME
    )

    changes_list = response['Changes']
    if not changes_list:
        print("No Changes found in Template/Parameter, Stack is Up-to-Date")
        return None, None, None, None, None
    else:
        change_set_list = convert_data(changes_list)
        return change_set_list



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


def create_stack(params,region):
    cf_template = open(TEMPLATE_BODY_FILE).read()
    client = boto3.client('cloudformation', region_name=region)
    try:
        response = client.create_stack(
            StackName=STACK_NAME,
            TemplateBody=cf_template,
            Parameters=params,
            Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND'],
            RoleARN=CF_ROLE_ARN
        )
        print("Provisioning new Stack.....")
        waiter = client.get_waiter('stack_create_complete')
        waiter.wait(StackName=STACK_NAME)
        describe_stack(STACK_NAME)
        return response

    except botocore.exceptions.ClientError as ex:
        error_message = ex.response['Error']['Message']

        stack_exists = "Stack ["+STACK_NAME+"] already exists"
        if error_message == stack_exists:
            return 'stack-exists'


def validate_change_set(region):
    change_set = get_change_set(region)
    if change_set:
        return "no-changes"
    else:
        print(json.dumps(change_set, indent=4))
        return change_set



def create_change_set(params,region):
    cf_template = open(TEMPLATE_BODY_FILE).read()
    client = boto3.client('cloudformation', region_name=region)
    try:
        response = client.create_change_set(
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




def approval(change_set):
    # Create a step functions client
    client = boto3.client('stepfunctions', region_name='us-east-1')
    #Start the execution
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


def execute_stack_update(region):
    print("Executing Change Set is region: " + region)
    client = boto3.client('cloudformation', region_name=region)
    try:
        response = client.execute_change_set(
            ChangeSetName=CHANGE_SET_NAME+COMMIT_ID,
            StackName=STACK_NAME
        )

        #print(response)
        print("Stack Update in Progress...")
        try:
            waiter = client.get_waiter('stack_update_complete')
            waiter.wait(StackName=STACK_NAME)
            describe_stack(STACK_NAME)
        except botocore.exceptions.WaiterError as ex:
            describe_stack(STACK_NAME)

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


def stack_exists(response, region, parameters):
    if response == "stack-exists":
        print("Stack ["+STACK_NAME+"] already exists")
        print("Discovering new Changes")
        print(parameters)
        change_set_response = create_change_set(parameters, region)
        if change_set_response == "change-set-created":
            validate_change_set_response =  validate_change_set(region)
            ch_set = json.dumps(validate_change_set_response)
            print(ch_set)
            #response = approval(json.dumps(validate_change_set_response))
            if validate_change_set_response == "no-changes":
                print("running no change block")
                exit(0)

    return response, ch_set

if sys.argv[1] == "update":
    parameters_ue1 = read_parameters_json(PARAMS_FILE_UE1)
    create_stack_response = create_stack(parameters_ue1, 'us-east-1')
    stack_exists_response_ue1, change_set_ue1 = stack_exists(create_stack_response, 'us-east-1', parameters_ue1 )


    # if response == "stack-exists":
    #     print("Stack ["+STACK_NAME+"] already exists")
    #     print("Discovering new Changes")
    #     change_set_response = create_change_set(parameters,'us-east-1')
    #     if change_set_response == "change-set-created":
    #         validate_change_set_response =  validate_change_set()
    #         #print(type(validate_change_set_response))
    #         #print(type(ch_set))
    #
    #
    #         ch_set = json.dumps(validate_change_set_response)
    #         response = approval(json.dumps(validate_change_set_response))
    #         with open(filename, 'w') as f:
    #             f.write(response)
    #             #json.dump(response, f)
    #         if validate_change_set_response == "no-changes":
    #             exit(0)

    print(json.dumps(stack_exists_response_ue1, indent=4))
    print(json.dumps(change_set_ue1, indent=4))

    # with open(filename, 'w') as f:
    #     f.write(response)


elif sys.argv[1] == "execute":
    print("Executing Change Set")

    with open(filename, "r") as file:
        data_string = file.read()
    data = json.loads(data_string)
    print(type(data))

    if data['Status'] == 'Approved' and data['Region'] == 'ue1':
        execute_stack_update('us-east-1')
    elif data['Status'] == 'Approved' and data['Region'] == 'ue2':
        execute_stack_update('us-east-2')
    elif data['Status'] == 'Approved' and data['Region'] == 'both':
        execute_stack_update('us-east-1')
        execute_stack_update('us-east-2')
    elif data['Status'] == 'Rejected' and data['Region'] == 'both':
        client = boto3.client('cloudformation', region_name=REGION)
        print("Stack Update Rejected, Deleting the current change Set created !")
        response = client.delete_change_set(
            ChangeSetName=CHANGE_SET_NAME + COMMIT_ID,
            StackName=STACK_NAME
        )
        print(CHANGE_SET_NAME + COMMIT_ID + " ChangeSet Deleted !")








# elif sys.argv[1] == "approval":
#     print("Approval")
#
#     print(data)






















