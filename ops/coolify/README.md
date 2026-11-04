# Open Wearables 0.11 on Coolify

Use the Git application's Docker Compose build pack, repository root, and
`/docker-compose.prod.yml`. The backend image is built from this fork; the
upstream image does not contain the fork's training routes or merge revision.

## Separate staging resource

Create a fresh Git application for this branch. Use empty, resource-scoped
PostgreSQL and Redis volumes and synthetic accounts. Never attach a production
database clone to an internet-connected worker or Beat: scheduled jobs can
contact providers with stored credentials. Rehearse a restored database on a
separate internal network with no published ports and no external credentials.

Use a distinct `OW_IMAGE_PREFIX` (e.g. `meala-ow-staging`), unique
`OW_API_BIND` and `OW_PORTAL_BIND` (e.g. `127.0.0.1:58101` and
`127.0.0.1:58301`) and an unused `OW_FLOWER_PORT` (e.g. `58556`).
The backend and portal use internal ports 8000 and 3000. Assign only staging
domains if public access is needed. Set separate DB and admin passwords, a
separate `SECRET_KEY`, staging-only API/portal URLs and CORS origins.
Keep outgoing webhooks off and production Garmin credentials out of staging.

## Production cutover

1. Confirm the deployed revision in Coolify and record the actual container
   mounts, public URLs and previous image IDs. Preserve the production resource
   and its named volumes (`postgres_data:/var/lib/postgresql`, `redis_data:/data`).
   Check the rendered service names and mount sources in Coolify. A differently
   named resource with an empty volume can look like a successful upgrade.
2. Preserve DB credentials, secret key, SDK application credentials, OAuth
   credentials, and any configured encryption key. Keep the existing API and
   portal domains. Set `API_BASE_URL`, `FRONTEND_URL`, `CORS_ORIGINS`, and
   `VITE_API_URL` to the appropriate public URLs. The SvelteKit server uses
   `API_URL=http://app:8000` internally. Keep Flower bound to loopback.
3. Coordinate auto-deploy and a maintenance window. Quiesce writes and workers;
   save and verify a current restore point with the previous application
   revision. Alembic must start at the installed fork revision and reach
   `15cf3e67a04b`. Do not stamp over missing revisions. The API bootstrap also
   runs separate data migrations (including the Google provider split and
   duplicate-source/event repair); check their results even if the app is healthy.
4. Verify portal, API, worker queues and Beat. Test an old Android upload with
   provider `google`, an old Apple upload, session refresh and the database
   result. Test a real Garmin push, workout publication and the Meala readback.
   Keep Garmin's push URL on production and preserve its client-ID header.
   The fork's nine training operations remain; the old Garmin backfill
   retry/cancel endpoints were removed upstream.
5. Before wider iOS rollout, verify that replaying the same HealthKit UUID
   through both writers adds no duplicate. For already split Oura HR sources,
   review `oura-hr-repair.sql` on the restore copy first. It defaults to rollback,
   requires a single account, and aborts on conflicting or archived data. Run
   with writers quiesced. Review counts before authorizing a production commit.
6. Rollback after schema changes means restoring the verified pre-cutover DB
   and previous application revision together. Coordinate replay of any uploads
   received after the restore point before reopening traffic.
