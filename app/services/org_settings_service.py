from app.models.organization import OrganizationSettings


def get_active_organization_settings():
    try:
        settings = OrganizationSettings.query.filter_by(is_active=True).order_by(OrganizationSettings.id.desc()).first()
    except Exception:
        settings = None
    return settings or OrganizationSettings.empty()


get_organization_settings = get_active_organization_settings


def ensure_single_active_organization_settings():
    active_items = OrganizationSettings.query.filter_by(is_active=True).order_by(OrganizationSettings.id.asc()).all()
    if len(active_items) <= 1:
        return active_items[0] if active_items else None

    primary = active_items[0]
    for item in active_items[1:]:
        item.is_active = False
    return primary



def get_or_create_organization_settings():
    settings = OrganizationSettings.query.filter_by(is_active=True).order_by(OrganizationSettings.id.desc()).first()
    if settings:
        return settings
    settings = OrganizationSettings(is_active=True)
    return settings


def _clean(value):
    value = (value or '').strip()
    return value


def get_organization_header_lines(settings=None):
    settings = settings or get_active_organization_settings()
    lines = []
    parent_org_name = _clean(getattr(settings, 'parent_org_name', None))
    full_name = _clean(getattr(settings, 'full_name', None))
    short_name = _clean(getattr(settings, 'short_name', None))

    if parent_org_name:
        lines.append(parent_org_name)
    if full_name:
        lines.append(full_name)
    elif short_name:
        lines.append(short_name)

    address_parts = [
        _clean(getattr(settings, 'postal_code', None)),
        _clean(getattr(settings, 'city', None)),
        _clean(getattr(settings, 'address', None)),
    ]
    address_line = ', '.join(part for part in address_parts if part)
    if address_line:
        lines.append(address_line)

    contact_parts = []
    phone = _clean(getattr(settings, 'phone', None))
    fax = _clean(getattr(settings, 'fax', None))
    email = _clean(getattr(settings, 'email', None))
    website = _clean(getattr(settings, 'website', None))

    if phone and fax:
        contact_parts.append(f'Телефон/факс: {phone}, {fax}')
    elif phone:
        contact_parts.append(f'Телефон: {phone}')
    elif fax:
        contact_parts.append(f'Факс: {fax}')
    if email:
        contact_parts.append(f'e-mail: {email}')
    if website:
        contact_parts.append(f'сайт: {website}')
    if contact_parts:
        lines.append(' · '.join(contact_parts))

    requisite_parts = []
    okpo = _clean(getattr(settings, 'okpo', None))
    ogrn = _clean(getattr(settings, 'ogrn', None))
    inn = _clean(getattr(settings, 'inn', None))
    kpp = _clean(getattr(settings, 'kpp', None))
    if okpo:
        requisite_parts.append(f'ОКПО {okpo}')
    if ogrn:
        requisite_parts.append(f'ОГРН {ogrn}')
    if inn and kpp:
        requisite_parts.append(f'ИНН/КПП {inn}/{kpp}')
    elif inn:
        requisite_parts.append(f'ИНН {inn}')
    elif kpp:
        requisite_parts.append(f'КПП {kpp}')
    if requisite_parts:
        lines.append(', '.join(requisite_parts))

    return [line for line in lines if line]


def get_organization_signature_block(settings=None):
    settings = settings or get_active_organization_settings()
    position = _clean(getattr(settings, 'director_position', None)) or 'Руководитель'
    name = _clean(getattr(settings, 'director_name', None))
    if name:
        return f'{position}     {name}'
    return position
