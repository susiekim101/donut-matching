import csv
import itertools
import random
import os
import requests
from dotenv import load_dotenv

load_dotenv()
GROUP_SIZE = 3
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]


def get_past_groups():
    # Load past groups (each row can have 2-4 names)
    with open("history.csv", newline="") as f:
        past_groups = [row for row in csv.reader(f)]
    return past_groups

def get_names():
    names = []
    response = requests.post("https://slack.com/api/conversations.members", 
                             headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                             params={"channel": "C048LJN8NKS"})
    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(f"Slack API error calling conversations.members: {data.get("error")}")
    
    for member_id in data["members"]:
        user_response = requests.get("https://slack.com/api/users.info",
                                 headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                                 params={"user": member_id})
        user_data = user_response.json()
        user = user_data["user"]

        if user.get("is_bot") or user.get("deleted"):
            continue

        names.append(user["real_name"])

    return names

# Begin the matching process
def build_forbidden(past_groups):
    return {
        frozenset(pair)
        for group in past_groups
        for pair in itertools.combinations(group, 2)
    }

def generate_new_groups(names, past_groups, group_size=GROUP_SIZE):
    names = names[:]
    random.shuffle(names)

    forbidden = build_forbidden(past_groups)

    unassigned = set(names)
    groups = []

    for name in names:
        if name not in unassigned:
            continue

        group = [name]
        unassigned.discard(name)
        candidates = [n for n in unassigned if frozenset((name, n)) not in forbidden]

        while len(group) < group_size and candidates:
            pick = candidates.pop()
            group.append(pick)
            unassigned.discard(pick)
            candidates = [n for n in candidates if frozenset((pick, n)) not in forbidden]

        if len(group) == group_size:
            groups.append(group)
        else:
            unassigned.update(group)

    # Anyone left couldn't complete a group without repeating a past pairing.
    # Force-group them anyway so nobody is left out.
    if unassigned:
        leftover = list(unassigned)
        random.shuffle(leftover)
        for i in range(0, len(leftover), group_size):
            groups.append(leftover[i:i + group_size])

    with open("pairings.csv", "w", newline="") as f:
        csv.writer(f).writerows(groups)
    with open("history.csv", "a", newline="") as f:
        csv.writer(f).writerows(groups)

    return groups

if __name__ == "__main__":
    past_groups = get_past_groups()
    print("Retrieved history.csv")
    names = get_names()
    print("Retrieved names from #bp-donuts")

    groups = generate_new_groups(names, past_groups, 3)
    print(groups)