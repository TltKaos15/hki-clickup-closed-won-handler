"""
ClickUp API client for the Closed Won handoff webhook.
"""

import requests
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://api.clickup.com/api/v2"


def _headers(token):
    return {
        "Authorization": token,
        "Content-Type": "application/json",
    }


def get_task(token, task_id):
    """Fetch a task by ID, including custom fields.

    Raises on non-200 response.
    """
    url = f"{BASE_URL}/task/{task_id}"
    logger.info(f"Fetching task {task_id}")
    resp = requests.get(url, headers=_headers(token))

    if resp.status_code == 404:
        raise TaskNotFoundError(f"Task {task_id} not found")
    resp.raise_for_status()

    data = resp.json()
    logger.info(f"Fetched task: {data.get('name')} (id: {task_id})")
    return data


def get_folder_lists(token, folder_id):
    """Get all lists in a folder.

    Tries GET /folder/{id} first, falls back to GET /folder/{id}/list
    if the lists array is empty (documented ClickUp quirk).
    """
    # Primary endpoint
    url = f"{BASE_URL}/folder/{folder_id}"
    logger.info(f"Fetching folder {folder_id}")
    resp = requests.get(url, headers=_headers(token))

    if resp.status_code == 404:
        raise FolderNotFoundError(f"Folder {folder_id} not found")
    resp.raise_for_status()

    data = resp.json()
    lists = data.get("lists", [])

    if lists:
        logger.info(f"Found {len(lists)} lists in folder via primary endpoint")
        return lists

    # Fallback endpoint
    logger.info("Primary endpoint returned empty lists, trying fallback")
    url = f"{BASE_URL}/folder/{folder_id}/list"
    resp = requests.get(url, headers=_headers(token))
    resp.raise_for_status()

    lists = resp.json().get("lists", [])
    logger.info(f"Found {len(lists)} lists in folder via fallback endpoint")
    return lists


def get_list_tasks(token, list_id):
    """Get all tasks in a list."""
    url = f"{BASE_URL}/list/{list_id}/task"
    logger.info(f"Fetching tasks in list {list_id}")
    resp = requests.get(url, headers=_headers(token))
    resp.raise_for_status()

    tasks = resp.json().get("tasks", [])
    logger.info(f"Found {len(tasks)} tasks in list")
    return tasks


def update_task_field(token, task_id, field_id, value):
    """Update a single custom field on a task.

    Returns True on success, False on failure (logs error but does not raise).
    """
    url = f"{BASE_URL}/task/{task_id}/field/{field_id}"
    payload = {"value": value}
    logger.info(f"Updating field {field_id} on task {task_id} with value: {value}")

    try:
        resp = requests.post(url, headers=_headers(token), json=payload)

        if resp.status_code == 429:
            logger.warning(f"Rate limited updating field {field_id}")
            return False

        if not resp.ok:
            logger.error(
                f"Failed to update field {field_id}: "
                f"{resp.status_code} {resp.text}"
            )
            return False

        logger.info(f"Successfully updated field {field_id}")
        return True

    except requests.RequestException as e:
        logger.error(f"Request error updating field {field_id}: {e}")
        return False


class TaskNotFoundError(Exception):
    pass


class FolderNotFoundError(Exception):
    pass
