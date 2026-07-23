import enum


class SourceType(str, enum.Enum):
    website = "website"
    facebook = "facebook"
    telegram = "telegram"
    instagram = "instagram"


class OfferType(str, enum.Enum):
    discount = "discount"
    event = "event"


class DiscountType(str, enum.Enum):
    percent = "percent"
    fixed = "fixed"
    free = "free"


class OfferStatus(str, enum.Enum):
    pending_review = "pending_review"
    published = "published"
    rejected = "rejected"
    expired = "expired"


class AdminRole(str, enum.Enum):
    super_admin = "super_admin"
    moderator = "moderator"


class CreatedBy(str, enum.Enum):
    admin = "admin"
    crawler = "crawler"
    crawler_suggestion = "crawler_suggestion"


class SuggestionStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class BotAccountState(str, enum.Enum):
    active = "active"
    cooldown = "cooldown"
    banned = "banned"


class BlockedHostStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
