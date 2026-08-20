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
    special_price = "special_price"


# Discount types whose discount_value is REQUIRED (and must be empty for the rest):
# percent = N%, fixed = N грн off, special_price = the final price is N грн.
VALUE_DISCOUNT_TYPES = (DiscountType.percent, DiscountType.fixed, DiscountType.special_price)


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


class QueryTermStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
