import asyncio, asyncpg
from datetime import date

async def run():
    conn = await asyncpg.connect('postgresql://yugabyte:yugabyte@localhost:5433/prana')

    # Make TechCorp alumni
    await conn.execute(
        "UPDATE employee_master SET dol='2023-06-30'::date, status='INACTIVE' "
        "WHERE employee_uuid='40000000-0000-0000-0001-000000000001'"
    )
    print('TechCorp -> alumni')

    # ABCD Bank employee_master
    await conn.execute(
        "INSERT INTO employee_master "
        "(employee_uuid,employee_user_id,tenant_id,pan_token,enc_pan,enc_dek,"
        "emp_id_org,full_name,designation,department,grade,doj,dol,status,"
        "vault_completeness,can_push,created_at,updated_at) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,"
        "NOW()-INTERVAL'8 years',NOW()) ON CONFLICT DO NOTHING",
        '40000000-0000-0000-0001-000000000002',
        '30000000-0000-0000-0000-000000000001',
        '10000000-0000-0000-0000-000000000002',
        'pan_token_emp001','enc_pan_emp001','enc_dek_emp001',
        'ABCD0181','Rahul Sharma','Junior Analyst','Retail Banking','G2',
        date(2016,7,1), date(2020,1,31), 'INACTIVE', 72, False
    )
    print('ABCD Bank master inserted')

    # PQRS Fintech employee_master
    await conn.execute(
        "INSERT INTO employee_master "
        "(employee_uuid,employee_user_id,tenant_id,pan_token,enc_pan,enc_dek,"
        "emp_id_org,full_name,designation,department,grade,doj,dol,status,"
        "vault_completeness,can_push,created_at,updated_at) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,"
        "NOW()-INTERVAL'17 months',NOW()) ON CONFLICT DO NOTHING",
        '40000000-0000-0000-0001-000000000003',
        '30000000-0000-0000-0000-000000000001',
        '10000000-0000-0000-0000-000000000003',
        'pan_token_emp001','enc_pan_emp001','enc_dek_emp001',
        'PQRS0042','Rahul Sharma','Senior Software Engineer','Engineering','L5',
        date(2024,2,1), None, 'ACTIVE', 88, True
    )
    print('PQRS Fintech master inserted')

    # Docs helper
    async def ins_doc(doc_id, tenant_id, emp_uuid, doc_type, period, interval_str, fname):
        sql = (
            "INSERT INTO document "
            "(document_id,tenant_id,employee_uuid,pan_token,doc_type,doc_period,"
            "s3_key,s3_bucket,file_size_bytes,file_hash_sha256,"
            "virus_scan_status,nsfw_scan_status,csam_detected,"
            "pipeline_status,is_self_upload,is_deleted,pushed_at,routed_at,original_filename) "
            f"VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,"
            f"NOW()-INTERVAL'{interval_str}',NOW()-INTERVAL'{interval_str}',$17) ON CONFLICT DO NOTHING"
        )
        await conn.execute(
            sql,
            doc_id, tenant_id, emp_uuid, 'pan_token_emp001',
            doc_type, period,
            f'tenants/{tenant_id}/{emp_uuid}/{fname}', 'prana-docs-dev',
            204800, f'hash_{doc_id[:8]}',
            'CLEAN', 'CLEAN', False,
            'ROUTED', False, False,
            fname
        )

    abcd = '10000000-0000-0000-0000-000000000002'
    e2   = '40000000-0000-0000-0001-000000000002'
    pqrs = '10000000-0000-0000-0000-000000000003'
    e3   = '40000000-0000-0000-0001-000000000003'

    await ins_doc('d0000000-abcd-0001-0000-000000000001', abcd, e2, 'APPOINTMENT_LETTER', '2016-07', '8 years', 'Appointment_Letter_ABCD_2016.pdf')
    await ins_doc('d0000000-abcd-0002-0000-000000000001', abcd, e2, 'SALARY_SLIP',        '2019-11', '5 years 2 months', 'Salary_Slip_Nov_2019.pdf')
    await ins_doc('d0000000-abcd-0003-0000-000000000001', abcd, e2, 'SALARY_SLIP',        '2019-12', '5 years 1 month',  'Salary_Slip_Dec_2019.pdf')
    await ins_doc('d0000000-abcd-0004-0000-000000000001', abcd, e2, 'FORM_16',            'FY:2019-20', '5 years',       'Form_16_FY2019-20_ABCD.pdf')
    await ins_doc('d0000000-abcd-0005-0000-000000000001', abcd, e2, 'RELIEVING_LETTER',   '2020-01', '4 years 5 months', 'Relieving_Letter_ABCD_2020.pdf')
    await ins_doc('d0000000-abcd-0006-0000-000000000001', abcd, e2, 'EXPERIENCE_LETTER',  '2020-01', '4 years 5 months', 'Experience_Letter_ABCD_2020.pdf')
    print('ABCD docs inserted')

    await ins_doc('d3000000-0000-0001-0000-000000000001', pqrs, e3, 'OFFER_LETTER',        '2024-01', '17 months', 'Offer_Letter_PQRS_2024.pdf')
    await ins_doc('d3000000-0000-0002-0000-000000000001', pqrs, e3, 'APPOINTMENT_LETTER',  '2024-02', '16 months', 'Appointment_Letter_PQRS_2024.pdf')
    await ins_doc('d3000000-0000-0003-0000-000000000001', pqrs, e3, 'SALARY_SLIP',         '2025-03', '3 months',  'Salary_Slip_Mar_2025.pdf')
    await ins_doc('d3000000-0000-0004-0000-000000000001', pqrs, e3, 'SALARY_SLIP',         '2025-04', '2 months',  'Salary_Slip_Apr_2025.pdf')
    await ins_doc('d3000000-0000-0005-0000-000000000001', pqrs, e3, 'SALARY_SLIP',         '2025-05', '1 month',   'Salary_Slip_May_2025.pdf')
    await ins_doc('d3000000-0000-0006-0000-000000000001', pqrs, e3, 'INCREMENT_LETTER',    'FY:2025-26', '2 months', 'Increment_Letter_PQRS_FY2025.pdf')
    await ins_doc('d3000000-0000-0007-0000-000000000001', pqrs, e3, 'FORM_16',             'FY:2024-25', '1 month',  'Form_16_FY2024-25_PQRS.pdf')
    print('PQRS docs inserted')

    count = await conn.fetchval(
        "SELECT count(*) FROM document d "
        "JOIN employee_master em ON em.employee_uuid=d.employee_uuid "
        "WHERE em.employee_user_id='30000000-0000-0000-0000-000000000001' AND d.is_deleted=FALSE"
    )
    print(f'Total docs for emp 001: {count}')

    masters = await conn.fetch(
        "SELECT t.tenant_name,em.doj,em.dol,em.status,em.designation "
        "FROM employee_master em JOIN tenant t ON t.tenant_id=em.tenant_id "
        "WHERE em.employee_user_id='30000000-0000-0000-0000-000000000001' ORDER BY em.doj"
    )
    for m in masters:
        print(dict(m))

    await conn.close()

asyncio.run(run())
