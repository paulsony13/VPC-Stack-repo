import boto3
import json
import sys
import botocore
import time
import os


CHANGE_SET_NAME = 'StackChangeSet'
STACK_NAME = 'VPCStack'

def auth(REGION):
    client = boto3.client('cloudformation', region_name=REGION)
    return client


def get_change_set(region):
    try:
        waiter = auth(region).get_waiter('change_set_create_complete')
        waiter.wait(
            ChangeSetName=CHANGE_SET_NAME,
            StackName=STACK_NAME,
        )
    except botocore.exceptions.WaiterError as ex:
        pass

    response = auth(region).describe_change_set(
        ChangeSetName=CHANGE_SET_NAME,
        StackName=STACK_NAME
    )

    changes_list = response['Changes']
    if not changes_list:
        print("No Changes found in Template/Parameter in "+region+", Stack is Up-to-Date")
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


def send_ses(html_table):
    # Connect to the SES service
    client = boto3.client('ses', region_name='us-east-2')

    # Define the recipient, sender, and subject of the email
    to_email = "paul.sankoorikal13@gmail.com"
    from_email = "paul.sankoorikal13@gmail.com"
    subject = "Cloudformation Deployment - Approval - " +STACK_NAME
    response = client.send_email(
        Destination={
            'ToAddresses': [to_email, ],
        },
        Message={
            'Subject': {
                'Data': subject,
            },
            'Body': {
                'Html': {
                    'Data': html_table,
                },
            },
        },
        Source=from_email
    )
    return response


def change_set_html(json_data, region):
    # Parse the JSON data
    data = json_data
    # Create the HTML table
    if data :
        print("Running hange block")
        html_table = "<h3><strong>{} ChangeSet </strong></h3>".format(region)
        html_table += "<table border='1'>"
        html_table += "<tr>"
        html_table += "<th>SL</th>"
        html_table += "<th>Action</th>"
        html_table += "<th>PhysicalResourceId</th>"
        html_table += "<th>Replacement</th>"
        html_table += "<th>LogicalResourceId</th>"
        html_table += "</tr>"
        for item in data:
            html_table += "<tr>"
            html_table += "<td>{}</td>".format(item["SL"])
            html_table += "<td>{}</td>".format(item["Action"])
            html_table += "<td>{}</td>".format(item["PhysicalResourceId"])
            html_table += "<td>{}</td>".format(item["Replacement"])
            html_table += "<td>{}</td>".format(item["LogicalResourceId"])
            html_table += "</tr>"
        html_table += "</table>"
        return (html_table)

    else:
        print(data)
        print("Running no change block")
        html_table = "<h3><strong>{} ChangeSet </strong></h3>".format(region)
        html_table += "<table border='1'>"
        html_table += "<tr>"
        html_table += "<th>Changes</th>"
        html_table += "</tr>"
        html_table += "<tr>"
        html_table += "<td>No Change to be Updated</td>"
        html_table += "</tr>"
        html_table += "</table>"
        return (html_table)

    # Print the HTML table


ue1_changeset = change_set_html(get_change_set('us-east-1'), "UE1")
ue2_changeset = change_set_html(get_change_set('us-east-2'), "UE2")

ChangeSet = ue1_changeset + ue2_changeset


send_ses(ChangeSet)