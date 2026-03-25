Log in to the {{ institution }} website.
The username is x_username and the password is x_password.

Steps:
1. If there is a login form visible, fill in the username and password and submit. Some sites use a two-step login — they ask for the username first, then show the password field on a second screen. If you see only a username field, enter it and submit, then enter the password on the next screen. Always fill in BOTH username and password before moving on.
2. If the site shows a 2FA/verification prompt AFTER you have already entered the password (text code, email code, security question, push notification, etc.), call the request_human_assistance tool with a short prompt for what you need.
3. If request_human_assistance returns a code or answer, use it on the current verification screen and continue.
4. If request_human_assistance returns SKIPPED_BY_USER, stop immediately and skip this provider for now.
5. After login is complete (you can see account info, dashboard, or a welcome message), you are done.

Important:
- A password field is NOT a 2FA prompt. Only call request_human_assistance for verification challenges that appear AFTER you have submitted the password.
- If the page looks like a mobile site, look for a 'Desktop site' or 'Full site' link.
- If you are already logged in (dashboard visible), you are done immediately.
- Do NOT navigate away from the site after logging in.
