from datetime import datetime


# def start_coding():
#     print("Add more Python code to this script to extend functionality!")


# def date():
#     current_datetime = datetime.now()
#     return current_datetime


# def main():
#     start_coding()
#     print(date())


import os
import asana
from asana.rest import ApiException
from pprint import pprint
import json
import requests


def create_asana_task(
    api_client,
    section_id: str,
    project_id: str,
    name: str,
    notes: str | None = None,
):
    api_task_client = asana.TasksApi(api_client)

    body = {"data": {"name": name, "projects": [project_id]}}

    if notes is not None:
        body["data"]["notes"] = notes

    task = api_task_client.create_task(body, {})
    task_id = task["gid"]

    api_section_client = asana.SectionsApi(api_client)
    api_section_client.add_task_for_section(
        section_id, {"body": {"data": {"task": task_id}}}
    )
    return task


def move_asana_task_to_section(api_client, task_id: str, section_id: str):
    api_section_client = asana.SectionsApi(api_client)

    return api_section_client.add_task_for_section(
        section_id, {"body": {"data": {"task": task_id}}}
    )


ASANA_PAT = os.getenv("ASANA_PAT")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
EVENT_NAME = os.getenv("GITHUB_EVENT_NAME")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")

ASANA_PROJECT_ID = os.getenv("INPUT_ASANA_PROJECT_ID")
ASANA_SECTION_TO_DO = os.getenv("INPUT_ASANA_SECTION_TO_DO")
ASANA_SECTION_DONE = os.getenv("INPUT_ASANA_SECTION_DONE")
ASANA_WORKSPACE_ID = os.getenv("INPUT_ASANA_WORKSPACE_ID")
ASANA_CUSTOM_FIELD_STATUS_ID = os.getenv("INPUT_ASANA_CUSTOM_FIELD_STATUS_ID")
ASANA_CUSTOM_FIELD_STATUS_IN_PROGRESS_ID = os.getenv(
    "INPUT_ASANA_CUSTOM_FIELD_STATUS_IN_PROGRESS_ID"
)
ASANA_CUSTOM_FIELD_STATUS_RESOLVED_ID = os.getenv(
    "INPUT_ASANA_CUSTOM_FIELD_STATUS_RESOLVED_ID"
)
ISSUE_NUMBER = os.getenv("INPUT_ISSUE_NUMBER")

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

configuration = asana.Configuration()
configuration.access_token = ASANA_PAT
api_client = asana.ApiClient(configuration)


def _is_already_synced(comments_url: str) -> bool:
    response = requests.get(comments_url, headers=headers)
    if response.status_code == 200:
        for comment in response.json():
            if "Asana Task ID:" in comment["body"]:
                return True
    return False


def _create_task_and_comment(title: str, body: str | None, comments_url: str):
    asana_task_name = title.split("Asana:")[1].strip() if title.startswith("Asana:") else title
    asana_task = create_asana_task(
        api_client,
        ASANA_SECTION_TO_DO,
        ASANA_PROJECT_ID,
        asana_task_name,
        body,
    )
    data = {"body": "Asana Task ID: %s" % asana_task["gid"]}
    response = requests.post(comments_url, json=data, headers=headers)
    if response.status_code == 201:
        print("Comment created successfully")
    else:
        print(f"Failed to create comment: {response.status_code}")


def handle_workflow_dispatch():
    if not ISSUE_NUMBER:
        print("INPUT_ISSUE_NUMBER not provided for workflow_dispatch")
        return
    if not GITHUB_REPOSITORY:
        print("GITHUB_REPOSITORY environment variable is not set")
        return

    issue_url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/{ISSUE_NUMBER}"
    response = requests.get(issue_url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to fetch issue #{ISSUE_NUMBER}: {response.status_code}")
        return

    issue_data = response.json()
    title = issue_data["title"]
    body = issue_data.get("body")
    comments_url = issue_data["comments_url"]

    if _is_already_synced(comments_url):
        print(f"Issue #{ISSUE_NUMBER} is already synced to Asana")
        return

    print(f"Syncing issue #{ISSUE_NUMBER} to Asana")
    _create_task_and_comment(title, body, comments_url)


def run():
    if EVENT_NAME == "workflow_dispatch":
        handle_workflow_dispatch()
        return

    with open("/github/workflow/event.json", "r") as file:
        event_data = json.load(file)
        # pprint(event_data, indent=2)

        action = event_data["action"]
        title = ""
        body = ""
        commit_url = ""

        if "issue" in event_data:
            commit_url = event_data["issue"]["comments_url"]
            title = event_data["issue"]["title"]
            body = event_data["issue"]["body"]
        else:
            commit_url = event_data["pull_request"]["_links"]["comments"]["href"]
            title: str = event_data["pull_request"]["title"]
            body: str | None = event_data["pull_request"]["body"]

        # base_branch = event_data["pull_request"]["base"]["ref"]
        # pprint("Base branch: ", base_branch, action)

        if action == "opened":
            pprint("Pull request opened")

            if title.startswith("Asana:"):
                asana_task_name = title.split("Asana:")[1].strip()
                asana_task = create_asana_task(
                    api_client,
                    ASANA_SECTION_TO_DO,
                    ASANA_PROJECT_ID,
                    asana_task_name,
                    body,
                )

                data = {"body": "Asana Task ID: %s" % asana_task["gid"]}

                response = requests.post(commit_url, json=data, headers=headers)

                if response.status_code == 201:
                    print("Comment created successfully")
                else:
                    print(f"Failed to create comment: {response.status_code}")

        elif action == "edited":
            if title.startswith("Asana:") and not _is_already_synced(commit_url):
                print("Issue/PR edited with Asana prefix — syncing to Asana")
                _create_task_and_comment(title, body, commit_url)

        elif action == "closed":
            pprint("Pull request closed")

            response = requests.get(commit_url, headers=headers)
            if response.status_code == 200:
                comments = response.json()
                for comment in comments:
                    if "Asana Task ID:" in comment["body"]:
                        asana_task_id = (
                            comment["body"].split("Asana Task ID:")[1].strip()
                        )

                        try:
                            move_asana_task_to_section(
                                api_client,
                                asana_task_id,
                                ASANA_SECTION_DONE,
                            )
                        except ApiException as e:
                            print(e)
                        break
            else:
                pprint(f"Failed to fetch comments: {response.status_code}")


if __name__ == "__main__":
    run()
