-- One account at a time, in a maintenance window after the 0.11 migration.
-- psql -X -v account=<OW UUID> [-v apply=1] -f oura-hr-repair.sql
\set ON_ERROR_STOP on
\if :{?apply}
\else
\set apply 0
\endif
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='60s';
-- Prevent concurrent SDK imports or rollups from changing the reviewed set.
LOCK TABLE data_source, series_sample, series_aggregate, data_point_series_archive,
           series_sample_backup IN SHARE ROW EXCLUSIVE MODE;
CREATE TEMP TABLE repair_pair ON COMMIT DROP AS
SELECT old.id AS canonical, new.id AS alias FROM data_source old
JOIN data_source new ON new.user_id=old.user_id AND new.provider=old.provider
 AND new.device_model IS NOT DISTINCT FROM old.device_model
WHERE old.user_id=:'account'::uuid AND old.provider='apple'
 AND old.source='com.ouraring.oura' AND new.source='Oura'
 AND old.device_id IS NULL AND new.device_id IS NULL
 AND old.source_app_id IS NULL AND new.source_app_id IS NULL
 AND EXISTS (
   SELECT FROM series_sample a JOIN series_sample b
    ON a.external_id=b.external_id AND a.recorded_at=b.recorded_at
    AND a.series_type_definition_id=b.series_type_definition_id
   WHERE a.data_source_id=old.id AND b.data_source_id=new.id AND a.series_type_definition_id=1
 );
DO $$
BEGIN
 IF (SELECT count(*) FROM repair_pair)>1 THEN RAISE EXCEPTION 'Ambiguous source pairs'; END IF;
 IF EXISTS (SELECT FROM repair_pair p JOIN series_sample b ON b.data_source_id=p.alias
   LEFT JOIN series_sample a ON a.data_source_id=p.canonical AND a.series_type_definition_id=1
    AND (a.recorded_at=b.recorded_at OR a.external_id=b.external_id)
   WHERE b.series_type_definition_id=1 AND (b.external_id IS NULL OR b.external_id=''
    OR (a.id IS NOT NULL AND ROW(a.external_id,a.recorded_at,a.value,a.zone_offset,a.window_seconds,a.is_daily_total)
       IS DISTINCT FROM ROW(b.external_id,b.recorded_at,b.value,b.zone_offset,b.window_seconds,b.is_daily_total))))
 THEN RAISE EXCEPTION 'Conflicting sample identity or values'; END IF;
 IF EXISTS (SELECT FROM repair_pair p JOIN series_aggregate x ON x.data_source_id IN (p.alias,p.canonical) WHERE x.series_type_definition_id=1)
 OR EXISTS (SELECT FROM repair_pair p JOIN data_point_series_archive x ON x.data_source_id IN (p.alias,p.canonical) WHERE x.series_type_definition_id=1)
 OR EXISTS (SELECT FROM repair_pair p JOIN series_sample_backup x ON x.data_source_id IN (p.alias,p.canonical) WHERE x.series_type_definition_id=1)
 THEN RAISE EXCEPTION 'Derived or archived HR exists; review before moving samples'; END IF;
END $$;
DELETE FROM series_sample b USING repair_pair p, series_sample a
WHERE b.data_source_id=p.alias AND a.data_source_id=p.canonical
 AND b.series_type_definition_id=1 AND a.series_type_definition_id=1
 AND a.external_id=b.external_id AND a.recorded_at=b.recorded_at;
UPDATE series_sample b SET data_source_id=p.canonical FROM repair_pair p
WHERE b.data_source_id=p.alias AND b.series_type_definition_id=1;
UPDATE data_source s SET source_app_id='com.ouraring.oura' FROM repair_pair p WHERE s.id=p.canonical;
\if :apply
COMMIT;
\else
ROLLBACK;
\endif
