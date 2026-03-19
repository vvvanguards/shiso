Go to the {{ institution }} website.

Log in with username x_username and password x_password. If you are already logged in, verify the account belongs to x_username. If it belongs to a different user, log out first and then log in with the correct credentials.

If you encounter a 2FA prompt, verification code screen, CAPTCHA, or any security challenge you cannot complete yourself, call the pause_for_human action and wait.
{% if dashboard_url %}

After logging in, navigate to {{ dashboard_url }}.
{% endif %}
