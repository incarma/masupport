# commission/migrations/0025_fix_rateexamplepayrow_columns.py
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("commission", "0024_rateexamplepayrow"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'commission_rateexamplepayrow'
                      AND column_name = 'col_a'
                ) THEN
                    ALTER TABLE commission_rateexamplepayrow
                    RENAME COLUMN col_a TO col_first;
                END IF;

                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'commission_rateexamplepayrow'
                      AND column_name = 'col_b'
                ) THEN
                    ALTER TABLE commission_rateexamplepayrow
                    RENAME COLUMN col_b TO col_yr1;
                END IF;

                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'commission_rateexamplepayrow'
                      AND column_name = 'col_c'
                ) THEN
                    ALTER TABLE commission_rateexamplepayrow
                    RENAME COLUMN col_c TO col_m13;
                END IF;

                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'commission_rateexamplepayrow'
                      AND column_name = 'col_d'
                ) THEN
                    ALTER TABLE commission_rateexamplepayrow
                    RENAME COLUMN col_d TO col_yr2;
                END IF;

                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'commission_rateexamplepayrow'
                      AND column_name = 'col_e'
                ) THEN
                    ALTER TABLE commission_rateexamplepayrow
                    RENAME COLUMN col_e TO col_yr3;
                END IF;

                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'commission_rateexamplepayrow'
                      AND column_name = 'col_f'
                ) THEN
                    ALTER TABLE commission_rateexamplepayrow
                    RENAME COLUMN col_f TO col_m36;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'commission_rateexamplepayrow'
                      AND column_name = 'col_m37'
                ) THEN
                    ALTER TABLE commission_rateexamplepayrow
                    ADD COLUMN col_m37 numeric(12,4) NULL;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'commission_rateexamplepayrow'
                      AND column_name = 'col_yr4'
                ) THEN
                    ALTER TABLE commission_rateexamplepayrow
                    ADD COLUMN col_yr4 numeric(12,4) NULL;
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]