import csv
import itertools
import random
import os
import requests
from dotenv import load_dotenv

load_dotenv()
GROUP_SIZE = 3
FRESHNESS = 3  # number of most recent rounds to keep in history.csv
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL_ID = os.environ["SLACK_CHANNEL_ID"]


def get_past_groups():
    # Load past groups (each row is a round number followed by 2-4 names)
    with open("history.csv", newline="") as f:
        past_groups = [row[1:] for row in csv.reader(f) if row]
    return past_groups

def get_names():
    names = []
    response = requests.post("https://slack.com/api/conversations.members", 
                             headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                             params={"channel": SLACK_CHANNEL_ID})
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

    return groups

def get_next_round():
    # Next round is one more than the highest round number in history.csv
    with open("history.csv", newline="") as f:
        rounds = [int(row[0]) for row in csv.reader(f) if row and row[0].isdigit()]
    return max(rounds, default=0) + 1

def remove_stale_groups(current_round, freshness=FRESHNESS):
    # Drop groups from rounds older than the last `freshness` rounds,
    # so those people can be paired together again
    with open("history.csv", newline="") as f:
        rows = [row for row in csv.reader(f) if row]
    fresh = [row for row in rows if int(row[0]) > current_round - freshness]
    with open("history.csv", "w", newline="") as f:
        csv.writer(f).writerows(fresh)

def save_groups(groups):
    # Overwrite pairings.csv with this round's groups
    with open("pairings.csv", "w", newline="") as f:
        csv.writer(f).writerows(groups)

    # Append to history.csv with the next round number, making sure we start on a new line
    round_num = get_next_round()
    with open("history.csv", "a+", newline="") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() > 0:
            f.seek(f.tell() - 1)
            if f.read(1) not in ("\n", "\r"):
                f.write("\n")
        csv.writer(f).writerows([round_num, *group] for group in groups)

    remove_stale_groups(round_num)

if __name__ == "__main__":
    past_groups = get_past_groups()
    print("Retrieved history.csv")
    names = get_names()
    print("Retrieved names from #bp-donuts")

    groups = generate_new_groups(names, past_groups, 3)
    print(groups)

    save_groups(groups)
    print("Saved groups to pairings.csv and history.csv")