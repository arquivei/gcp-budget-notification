import base64
import json
import os
import slack
from slack.errors import SlackApiError

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from datetime import datetime

# Firebase configuration
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred, {
  'projectId': os.environ['GCP_FIREBASE_PROJECT'],
})
firebase_db = firestore.client()
DB_COLLECTION=u'budget_alerts'

# See https://api.slack.com/docs/token-types#bot for more info
BOT_ACCESS_TOKEN = os.environ['SLACK_BOT_TOKEN']
SLACK_CHANNEL = os.environ['SLACK_NOTIFY_CHANNEL']

ORGANIZATION_ID = os.environ['GCP_ORG_ID']

slack_client = slack.WebClient(token=BOT_ACCESS_TOKEN)
def budget_alert(data, context):
    pubsub_message = data

    try:
        notification_attr = pubsub_message['attributes']
    except KeyError:
        notification_attr = "No attributes passed in"

    try:
        notification_data = json.loads(base64.b64decode(data['data']).decode('utf-8'))
    except KeyError:
        notification_data = "No data passed in"

    current_threshold = get_current_threshold(notification_data['costAmount']/notification_data['budgetAmount'])
    last_threshold = get_last_threshold(notification_data['costIntervalStart'])
    if check_should_alert(current_threshold, last_threshold):
        try:
            fallback_text = "```{}```".format(json.dumps(notification_data, indent=2))
            message = format_message(notification_data, notification_attr, fallback_text)
            send_message(message)

            save_threshold(notification_data['costIntervalStart'], current_threshold)
        except SlackApiError as e:
            print('Error posting to Slack')
            print(e)
        except Exception as e:
            print('Generic error')
            print(e)

def send_message(message):
    slack_client.api_call(
        'chat.postMessage',
        json=message
    )

# @see https://app.slack.com/block-kit-builder/ for helper to build and the following link to this example
# @see https://app.slack.com/block-kit-builder/T02FVQGP8#%7B%22blocks%22:%5B%7B%22type%22:%22header%22,%22text%22:%7B%22type%22:%22plain_text%22,%22text%22:%22:warning:%20GrossMargin-Expected%22,%22emoji%22:true%7D%7D,%7B%22type%22:%22section%22,%22text%22:%7B%22type%22:%22mrkdwn%22,%22text%22:%22A%20new%20budget%20alert%20was%20triggered%20with%20the%20following%20contents%22%7D%7D,%7B%22type%22:%22divider%22%7D,%7B%22type%22:%22section%22,%22fields%22:%5B%7B%22type%22:%22mrkdwn%22,%22text%22:%22*Current%20Amount:*%5CnR$%2092633.46%22%7D,%7B%22type%22:%22mrkdwn%22,%22text%22:%22*Total%20Amount:*%5CnR$%20300000.0%22%7D,%7B%22type%22:%22mrkdwn%22,%22text%22:%22*Triggered:*%5CnMar%2010,%202015%22%7D%5D%7D,%7B%22type%22:%22divider%22%7D,%7B%22type%22:%22section%22,%22text%22:%7B%22type%22:%22mrkdwn%22,%22text%22:%22Check%20the%20current%20billing%20report%22%7D,%22accessory%22:%7B%22type%22:%22button%22,%22text%22:%7B%22type%22:%22plain_text%22,%22text%22:%22View%20report%22,%22emoji%22:true%7D,%22value%22:%22click_me_123%22,%22url%22:%22https://console.cloud.google.com/billing/012424-7A39CC-A49028/reports?organizationId=185385634726&orgonly=true&project=arquivei-registry&supportedpurview=project%22,%22action_id%22:%22button-action%22%7D%7D%5D%7D
def format_message(data, attributes, fallback_text):
    return {
        "channel": SLACK_CHANNEL,
        "text": fallback_text,
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":warning: {}".format(data['budgetDisplayName']),
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "A new budget alert was triggered with the following contents"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": "*Current Amount:*\nR$ {:.2f}".format(data['costAmount'])
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*Total Amount:*\nR$ {:.2f}".format(data['budgetAmount'])
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*Reached:*\n {:.2f}%".format(data['costAmount']*100/data['budgetAmount'])
                    }
                ]
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Check the current billing report"
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View report",
                        "emoji": True
                    },
                    "value": "",
                    "url": "https://console.cloud.google.com/billing/{}/reports?organizationId={}&orgonly=true&supportedpurview=project".format(attributes['billingAccountId'], ORGANIZATION_ID),
                    "action_id": "button-action"
                }
            }
        ]
    }

def get_last_threshold(month):
    doc_ref = firebase_db.collection(DB_COLLECTION).document(month)
    doc = doc_ref.get()

    if doc.exists:
        return doc.to_dict()[u'threshold']

    return None

def save_threshold(month, threshold):
    doc_ref = firebase_db.collection(DB_COLLECTION).document(month)
    doc_ref.set({
        u'threshold': threshold,
        u'occurredOn': datetime.now()
    })

def check_should_alert(current_threshold, last_threshold):
    if current_threshold == .5 and last_threshold is None:
        return True
    elif current_threshold == .75 and (last_threshold is None or last_threshold < .75):
        return True
    elif (current_threshold == 1 and last_threshold != 1):
        return True
    return False

def get_current_threshold(current_threshold):
    if current_threshold >= 1:
        return 1
    elif current_threshold >= .75:
        return .75
    elif current_threshold >= .5:
        return .5

    return None
