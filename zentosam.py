#!/usr/bin/python3

"""Python code to transfer helpdesk tickets from Zendesk to Samanage.

Tickets created on Samanage from tickets in Zendesk will have the name
of the ticket, who requested it, the priority of the ticket,
the assignee and the description. Comments from Zendesk
are added as comments to Samanage (The author of the comments on Samanage
will be the account whose Samanage account credentials are used in this code)."""

import json
import math
import sys
import time

import requests



class Samanage(object):
    """Class for Samanage API.

    Samanage uses HTTP Digest for authentication
    which takes username and password."""
    def __init__(self, username, password):
        self.uri = "https://api.samanage.com"
        self.session = requests.Session()
        self.session.auth = requests.auth.HTTPDigestAuth(username, password)
        self.session.headers = {"Accept":"application/vnd.samanage.v1.1+json",
                                "Content-Type":"application/json"}

    def incident(self, name, requester, priority, status, assignee, description):
        """Create an incident on Samanage. Name, requestor and priority
        are requried fields."""
        payload = {
            "incident":{
                "name": name,
                "requester": {"email": requester},
                "priority": priority,
                "state": status,
                "assignee":{"email": assignee},
                "description": description
            }
        }
        response = self.session.post(
            "{0}/incidents.json".format(self.uri),
            json=payload
        )
        return response.text

    def comment(self, body, incident_id):
        """Create a comment on a Samanage incident."""
        payload = {"comment":{"body":body, "is_private":"false"}}
        response = self.session.post(
            "{0}/incidents/{1}/comments.json".format(self.uri, incident_id),
            json=payload
        )
        return response.status_code

    def update_status(self, value, incident_id):
        """Update an incident's state on Samanage."""
        payload = {"incident":{"state": value}}
        response = self.session.put(
            "{0}/incidents/{1}.json".format(self.uri, incident_id),
            json=payload
        )
        return response.status_code


class Zendesk(object):
    """Class for Zendesk API.

    Zendesk authentication will accept username with password
    or api token. If using api token set token argument to True
    when initalizing class.

    Zendesk returns api calls in html. Responses are
    read as binary instead and to prevent UnicodeDecodeError
    are decoded with 'replace' argument."""
    def __init__(self, username, password, org, token=False):
        self.username = username
        self.password = password
        self.token = token
        self.uri = "https://{0}.zendesk.com/api/v2".format(org)
        self.session = requests.Session()
        if self.token:
            self.session.auth = username+"/token", password
        else:
            self.session.auth = username, password
        self.session.headers = {"Content-Type":"application/json"}

    def http_call(self, request):
        """Make HTTP GET request to Zendesk.

        Zendesk has rate-limits and will return a 429 Too Many Requests response
        once its hit. This response is caught and the code will wait before
        resending the request.

        Zendesk rate-limits are listed at:
        https://developer.zendesk.com/rest_api/docs/core/introduction#rate-limits

        HTTP errors are raised to console."""
        response = self.session.get(request)
        attempts = 0
        while response.status_code == 429:
            if attempts > 5:
                break
            attempts = attempts + 1
            time.sleep(30)
            response = self.session.get(request)
        response.raise_for_status()
        return response

    def ticket_range(self):
        """Zendesk returns 100 tickets at a time. With this request we
        can calculate how many times we'd need to make a
        self.get_list_of_tickets request."""
        response = self.http_call("{0}/tickets.json".format(self.uri))
        return math.ceil(response.json()["count"] / 100) + 1

    def get_ticket(self, ticket_id):
        """Get a single ticket from Zendesk using the ticket id."""
        response = self.http_call("{0}/tickets/{1}.json".format(self.uri, ticket_id))
        return json.loads(response.content.decode(sys.stdout.encoding, "replace"))

    def get_assignee_email(self, assignee_id):
        """Get an assignee email using the assignee id."""
        response = self.http_call("{0}/users/{1}.json".format(self.uri, assignee_id))
        return json.loads(response.content.decode(sys.stdout.encoding, "replace"))["user"]["email"]

    def get_comments(self, ticket_id):
        """Get all the comments on a ticket using the ticket id."""
        response = self.http_call("{0}/tickets/{1}/comments.json".format(self.uri, ticket_id))
        return json.loads(response.content.decode(sys.stdout.encoding, "replace"))

    def get_list_of_tickets(self, page=1):
        """Get a list of tickets up to 100. Page argument used to view next 100."""
        response = self.http_call("{0}/tickets.json?page={1}".format(self.uri, page))
        return json.loads(response.content.decode(sys.stdout.encoding, "replace"))

    def get_comment_author(self, author_id):
        """Get the author of a comment using the author id."""
        response = self.http_call("{0}/users/{1}.json".format(self.uri, author_id))
        return json.loads(response.content.decode(sys.stdout.encoding, "replace"))["user"]["name"]

    def get_many_tickets(self, tickets):
        """Get many tickets from zendesk. Up to 100."""
        response = self.http_call("{0}/tickets/show_many.json?ids={1}".format(self.uri, tickets))
        return json.loads(response.content.decode(sys.stdout.encoding, "replace"))

    def get_all_ticket_ids(self):
        """"Function to just get all the ticket ids on zendesk as a list"""
        ticket_range = self.ticket_range()
        all_ticket_ids = []
        for i in range(1, ticket_range):
            tickets = self.get_list_of_tickets(i)
            for ticket in tickets["tickets"]:
                all_ticket_ids.append(ticket["id"])
        return all_ticket_ids


class Zentosam(object):
    """Class for functions to transfer tickets.

    If samanage argument is given the initalized Samanage class
    zendesk cards will be transfered to Samanage.

        If tickets are going to be transfered to Samanage
        the priority of the tickets needs to be given.
        Priority is a requried field for Samanage tickets.
        Likewise the default_requester needs to be given.
        When a Zendesk ticket does not have a requester
        the default_requester is used. Samanage requires
        a requester in its tickets.

    If dump argument is True a JSON dump of the information
    that is transfered  will be created as ticket_dump.json.

    Both, either or neither (if you don't want to get any results)
    of the samanage or dump arguments need to be set. Running the code
    with just dump set can be used to get an idea of what will be
    transfered to Samanage without actually transfering anything."""
    def __init__(self, zendesk, samanage=False, priority=None, default_requester=None, dump=False):
        self.zendesk = zendesk
        self.samanage = samanage
        self.priority = priority
        self.default_requester = default_requester
        if self.samanage and self.priority is None:
            self.priority = input("Input Samanage priority: ")
        if self.samanage and default_requester is None:
            self.default_requester = input("Input Samanage default requester: ")
        self.dump = dump

    def batch_transfer(self):
        """Transfer all tickets from zendesk to samanage."""
        ticket_range = self.zendesk.ticket_range()
        for i in range(1, ticket_range):
            tickets = self.zendesk.get_list_of_tickets(i)
            for ticket in tickets["tickets"]:
                ticket_id = ticket["id"]
                self.transfer_ticket(ticket_id)

    def transfer_ticket(self, ticket_id):
        """Transfer a ticket from zendesk
        to samanage using the zendesk ticket id."""
        ticket = self.zendesk.get_ticket(ticket_id)
        subject = ticket["ticket"]["subject"]
        status = ticket["ticket"]["status"]
        description = ticket["ticket"]["description"]
        if ticket["ticket"]["assignee_id"] is not None:
            assignee_email = self.zendesk.get_assignee_email(ticket["ticket"]["assignee_id"])
        try:
            requester = ticket["ticket"]["via"]["source"]["from"]["address"]
        except KeyError:
            requester = self.default_requester
        # Terms for the status of a ticket on Samanage differ from those on Zendesk
        # When creating a ticket on Samanage through API only statuses allowed are Closed and New.
        # After the ticket is created status can be changed.
        if status in ("open", "pending"):
            status = "New"
            update_status = "Assigned"
        if status in ("closed", "solved"):
            status = "Closed"
            update_status = "Closed"
        # We can now make incident on Samanage
        if self.samanage:
            incident = self.samanage.incident(
                subject, requester, self.priority, status, assignee_email, description
            )
            incident_id = json.loads(incident)["id"]
        # Get all comments for a ticket on zendesk
        comments = self.zendesk.get_comments(ticket_id)
        comment_list = []
        for comment in comments["comments"]:
            author = self.zendesk.get_comment_author(comment["author_id"])
            if self.dump:
                comment_list.append({"author": author, "body": comment["body"]})
            # Transfer comment(s) to Samanage
            if self.samanage:
                self.samanage.comment("From:{0}\n{1}".format(author, comment["body"]), incident_id)
        # Adding comments to samanage ticket reopens it
        # (re)update the status of the ticket on samanage to specified status
        if self.samanage:
            self.samanage.update_status(update_status, incident_id)

        # JSON dump if initalized
        if self.dump:
            with open("ticket_dump.json", "a", errors='replace') as dump_file:
                card_details = {ticket_id:{
                    "id": ticket_id,
                    "subject": subject,
                    "requester": requester,
                    "status": status,
                    "assignee": assignee_email,
                    "description": description,
                    "comments": comment_list}}
                dump_file.write(json.dumps(card_details, ensure_ascii=False,
                                           sort_keys=True, indent=4))
