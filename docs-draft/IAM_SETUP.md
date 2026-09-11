# Setting up authentication for OpenATS

OpenATS authenticates with self-hosted JWT auth: `backend-py` issues and
verifies its own HS256-signed tokens against a `users` table (bcrypt
password hashes), and `frontend` stores the token in an httpOnly session
cookie. There is no external identity provider to sign up for.

## 1. Configure the backend's secret key

Copy `backend-py/.env.example` to `backend-py/.env` if you haven't already,
and set `SECRET_KEY` to a long random value (used to sign and verify access
tokens - anyone with this value can forge a valid session, so treat it like
a password and never commit it):

```bash
openssl rand -hex 32
```

Paste the output into `SECRET_KEY` in `backend-py/.env`. `JWT_ALGORITHM`
(`HS256`) and `ACCESS_TOKEN_EXPIRE_MINUTES` (`30`) can be left at their
defaults.

## 2. Configure the frontend

Copy `frontend/.env.example` to `frontend/.env` and point `OPENATS_API_URL`
/ `NEXT_PUBLIC_API_URL` at your running `backend-py` instance
(`http://localhost:8080` for local dev). No auth-specific variables are
needed here - the frontend never talks to an identity provider directly.

## 3. Create the first admin user

There's no sign-up flow: the very first user has to be created directly in
the database, since every user-management endpoint requires an
authenticated `super_admin` to call it. Run this from `backend-py/`:

```bash
python -m app.db.create_admin --email admin@example.com \
  --password 'SomeStrongPass1!' --first-name Admin --last-name User
```

The password must be at least 12 characters with an uppercase letter,
lowercase letter, digit, and special character.

## 4. Log in

Go to `http://localhost:3000/login` and sign in with the email/password you
just created. From there, use **Settings > User Management** to invite the
rest of your team (`Super Admin`, `Hiring Manager`, `Interviewer` roles are
assigned per user, not configured externally).

That's it 🎉 Authentication should now work - go ahead and try out the
application locally.
