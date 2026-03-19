from enum import Enum


class UserRole(str, Enum):
    citizen = "citizen"
    moderator = "moderator"


class IssueStatus(str, Enum):
    pending_ai = "pending_ai"
    approved = "approved"
    rejected = "rejected"
    in_progress = "in_progress"
    resolved = "resolved"
