
import boto3
import time

def approval():
    # Create a step functions client
    SF_ARN='arn:aws:states:us-east-1:631145538984:stateMachine:HumanApprovalLambdaStateMachine-VhajMy09OQvt'
    client = boto3.client('stepfunctions', region_name='us-east-1')
    #Start the execution
    response=client.start_execution(
        stateMachineArn=SF_ARN
    )
    execution_arn = response['executionArn']
    while True:
        response = client.describe_execution(
            executionArn=execution_arn
        )
        if response['status'] == 'SUCCEEDED':
            break
        elif response['status'] == 'FAILED':
            exit(1)
        time.sleep(5)
    response = client.get_execution_history(executionArn=execution_arn)
    for event in response['events']:
        if event['type'] == 'ExecutionSucceeded':
            print(event['executionSucceededEventDetails']['output'])

approval()