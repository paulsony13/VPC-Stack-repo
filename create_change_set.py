import boto3
import os


def lambda_handler(event, context):
    try:
        # Retrieve the StackName from the event
        # stack_name = event['CodePipeline.job']['data']['actionConfiguration']['configuration']['UserParameters']
        stack_name = 'VPCStack'

        # CloudFormation client for US-East-1 and US-East-2 regions
        cloudformation_us_east_1 = boto3.client('cloudformation', region_name='us-east-1')
        cloudformation_us_east_2 = boto3.client('cloudformation', region_name='us-east-2')

        # SES client
        ses = boto3.client('ses')

        # Email message body
        message = 'CloudFormation Change Sets for Stack: {}\n\n'.format(stack_name)

        # Check if change set exists in US-East-1 region
        try:
            us_east_1_change_set = cloudformation_us_east_1.describe_change_set(
                ChangeSetName='StackChangeSet',
                StackName=stack_name
            )
            message += 'Region: US-East-1\n'
            message += 'Change Set Name: StackChangeSet\n'
            message += 'Execution Status: {}\n'.format(us_east_1_change_set['ExecutionStatus'])
            message += 'Status Reason: {}\n\n'.format(us_east_1_change_set['StatusReason'])
        except cloudformation_us_east_1.exceptions.ChangeSetNotFound:
            message += 'Region: US-East-1\n'
            message += 'Change Set Name: StackChangeSet\n'
            message += 'Execution Status: No Change Set Found\n\n'
        except cloudformation_us_east_1.exceptions.ChangeSetEmpty:
            message += 'Region: US-East-1\n'
            message += 'Change Set Name: StackChangeSet\n'
            message += 'Execution Status: No Changes in Change Set\n\n'

        # Check if change set exists in US-East-2 region
        try:
            us_east_2_change_set = cloudformation_us_east_2.describe_change_set(
                ChangeSetName='StackChangeSet',
                StackName=stack_name
            )
            message += 'Region: US-East-2\n'
            message += 'Change Set Name: StackChangeSet\n'
            message += 'Execution Status: {}\n'.format(us_east_2_change_set['ExecutionStatus'])
            message += 'Status Reason: {}\n\n'.format(us_east_2_change_set['StatusReason'])
        except cloudformation_us_east_2.exceptions.ChangeSetNotFound:
            message += 'Region: US-East-2\n'
            message += 'Change Set Name: StackChangeSet\n'
            message += 'Execution Status: No Change Set Found\n\n'
        except cloudformation_us_east_2.exceptions.ChangeSetEmpty:
            message += 'Region: US-East-2\n'
            message += 'Change Set Name: StackChangeSet\n'
            message += 'Execution Status: No Changes in Change Set\n\n'

        print(message)
        # Send email with change set details
        ses.send_email(
            Source=os.environ['SENDER_EMAIL'],
            Destination={'ToAddresses': [os.environ['RECIPIENT_EMAIL']]},
            Message={
                'Subject': {'Data': 'CloudFormation Change Sets for Stack: {}'.format(stack_name)},
                'Body': {'Text': {'Data': message}}
            }
        )

        # Notify CodePipeline of success
        code_pipeline = boto3.client('codepipeline')
        job_id = event['CodePipeline.job']['id']
        code_pipeline.put_job_success_result(jobId=job_id)

    except Exception as e:
        # Notify CodePipeline of failure
        code_pipeline = boto3.client
