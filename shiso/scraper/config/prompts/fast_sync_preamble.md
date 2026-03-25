Log in to the {{ institution }} website using the provided credentials.

{% if dashboard_url %}
After logging in, navigate to {{ dashboard_url }}.
{% endif %}

If you encounter a 2FA prompt, verification code screen, CAPTCHA, or any security challenge you cannot complete yourself, call the pause_for_human action and wait.
