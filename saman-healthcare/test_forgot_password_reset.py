import sqlite3

from database import init_database, register_patient, verify_account_identity, reset_account_credentials, get_db


def test_verify_account_identity_and_reset_credentials():
    init_database()
    conn = sqlite3.connect('healthcare.db')
    conn.execute("DELETE FROM patient_accounts WHERE id LIKE 'TEST%'")
    conn.execute("DELETE FROM patients WHERE id LIKE 'TEST%'")
    conn.commit()
    conn.close()

    patient_id = 'TESTP001'
    register_patient(
        patient_id,
        'Test Patient',
        '+923001234567',
        'test@example.com',
        'Password123',
        30,
        'Male',
        'O+',
        '1234',
    )

    conn = sqlite3.connect('healthcare.db')
    conn.execute(
        "UPDATE patients SET date_of_birth = ?, aadhaar_last_4 = ? WHERE id = ?",
        ('1995-05-04', '6789', patient_id),
    )
    conn.commit()
    conn.close()

    assert verify_account_identity('patient', patient_id, '1995-05-04', '6789') is True
    assert verify_account_identity('patient', patient_id, '1995-05-05', '6789') is False

    success = reset_account_credentials('patient', patient_id, 'NewPass123', '4321')
    assert success is True

    conn = sqlite3.connect('healthcare.db')
    row = conn.execute(
        "SELECT password_hash, security_pin_hash FROM patient_accounts WHERE id = ?",
        (patient_id,),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] != '0'
    assert row[1] != '0'
