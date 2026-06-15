DELIVERY_BOTH = "both"
DELIVERY_MAX = "max"
DELIVERY_APP = "app"

VALID_DELIVERY_CHANNELS = {DELIVERY_BOTH, DELIVERY_MAX, DELIVERY_APP}


def user_delivery_channel(user) -> str:
    value = (getattr(user, "notification_delivery_channel", None) or DELIVERY_BOTH).strip()
    return value if value in VALID_DELIVERY_CHANNELS else DELIVERY_BOTH


def allows_max(user) -> bool:
    return user_delivery_channel(user) in {DELIVERY_BOTH, DELIVERY_MAX}


def allows_mobile_app(user) -> bool:
    return user_delivery_channel(user) in {DELIVERY_BOTH, DELIVERY_APP}
