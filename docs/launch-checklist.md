# Launch Checklist

## 1. Push To GitHub

This local repo already has clean commits on `main`. To publish it:

```bash
git remote add origin https://github.com/YOUR_USERNAME/civicscope.git
git push -u origin main
```

If using GitHub CLI:

```bash
gh repo create civicscope --private --source . --remote origin --push
```

Before pushing, update the temporary local commit author if desired:

```bash
git config user.name "Your Name"
git config user.email "your.email@example.com"
git commit --amend --reset-author --no-edit
```

## 2. Deploy Backend

Recommended path:

1. Create a Render Blueprint from the GitHub repo.
2. Use the root `render.yaml`.
3. Confirm the backend service points at `backend/Dockerfile`.
4. Set `CORS_ORIGINS` after the frontend URL exists.
5. Confirm `/health` returns `{"status":"ok"}`.

Before deploying, protect `main` in GitHub: require pull requests, at least one approval
when collaborators are present, conversation resolution, and the CI and CodeQL status
checks. Enable Dependabot security updates and confirm the scheduled keep-alive workflow
is active.

The backend Dockerfile runs:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

## 3. Deploy Frontend

Recommended path:

1. Import the same GitHub repo into Vercel.
2. Set Root Directory to `frontend`.
3. Set `NEXT_PUBLIC_API_URL` to the deployed backend URL.
4. Deploy.

The frontend project includes `frontend/vercel.json` with Next.js build settings.

## 4. Wire CORS

After Vercel deploys, update the backend environment variable:

```text
CORS_ORIGINS=https://YOUR-VERCEL-APP.vercel.app
```

Redeploy/restart the backend after changing CORS.

## 5. Smoke Test

- Open the frontend URL.
- Confirm the municipal map loads.
- Switch to Census tracts.
- Search `5350001.00`.
- Confirm the detail panel shows `Toronto census tract 0001.00`.
- Open the backend `/health` URL.
- Open browser devtools and confirm there are no API/CORS errors.
- Confirm responses include the production Content Security Policy and HSTS headers.
- Open `/api/transit-routes` and confirm its manifest reports the intended agency coverage.
- Confirm the uptime monitor or keep-alive workflow records a persistent health failure as a failed check.

## 6. Update Portfolio Links

Update the README with:

- GitHub repository URL
- Live frontend URL
- Live backend health URL
- Demo video or GIF
