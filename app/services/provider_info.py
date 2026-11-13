"""Contact details for Ahmi software firm, the company that builds and
supports School Manager.

Centralised here (rather than written directly into a template) so that the
License page, and anything shown alongside it later such as a footer or a
dedicated About page, always display the same name, number and links. When
the firm's website goes live, only ``PROVIDER['website_url']`` needs to
change here; every page that reads it updates automatically.
"""

from urllib.parse import quote

#: Shown on the License page under "About your software provider".
PROVIDER = {
    'name': 'Ahmi software firm',
    'whatsapp_display': '0336 1124412',
    # International format, no leading '+' and no spaces: what wa.me expects.
    'whatsapp_number': '923361124412',
    'email': 'ahmiitfirm@gmail.com',
    'linkedin_url': 'https://www.linkedin.com/in/mrahmadtalha',
    'linkedin_label': 'mrahmadtalha',
    # The firm has no public website yet; the page shows "Coming soon"
    # whenever this is empty instead of a dead link.
    'website_url': None,
}


def whatsapp_link(message=None):
    """A ``wa.me`` link to the firm's WhatsApp number.

    With ``message`` given, the chat opens pre-filled with that text (used
    for the referral "Ask about referral rewards" button); without it, a
    plain link to start a new chat (used for the general contact entry).
    """
    base = f"https://wa.me/{PROVIDER['whatsapp_number']}"
    return f"{base}?text={quote(message)}" if message else base
