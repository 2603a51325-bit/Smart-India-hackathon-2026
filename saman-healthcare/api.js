const TEE = {
    supportedPlatforms: ['windows', 'mac', 'android', 'ios', 'linux'],
    detect() {
        const agent = navigator.userAgent || '';
        const platform = navigator.platform || '';
        const isWindows = /Windows/i.test(platform) || /Win32|Win64/i.test(agent);
        const isMac = /Mac/i.test(platform) || /Macintosh/i.test(agent);
        const isAndroid = /Android/i.test(agent);
        const isIOS = /iPhone|iPad|iPod/i.test(agent) || /iOS/i.test(agent);
        const isLinux = /Linux/i.test(platform) || /Linux/i.test(agent);
        const runtimePlatform = isWindows ? 'windows' : isMac ? 'mac' : isAndroid ? 'android' : isIOS ? 'ios' : isLinux ? 'linux' : 'unknown';
        const supported = this.supportedPlatforms.includes(runtimePlatform);
        return {
            platform: runtimePlatform,
            deviceClass: ['android', 'ios'].includes(runtimePlatform) ? 'mobile' : 'desktop',
            trustedExecutionEnvironment: {
                supported,
                enabled: supported,
                name: supported ? 'TEE' : 'Unsupported',
                status: supported ? 'available' : 'not_available'
            }
        };
    }
};

/**
 * Healthcare API Helper
 * Handles all database API calls
 */

const API = {
    baseUrl: 'http://127.0.0.1:8000/api',

    // Patients API
    async getPatients() {
        try {
            const response = await fetch(`${this.baseUrl}/patients`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'get_all' })
            });
            const data = await response.json();
            return data.patients || [];
        } catch (e) {
            console.error('Error fetching patients:', e);
            return [];
        }
    },

    async getPatient(id) {
        try {
            const response = await fetch(`${this.baseUrl}/patients`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'get', patient_id: id })
            });
            const data = await response.json();
            return data.patient || null;
        } catch (e) {
            console.error('Error fetching patient:', e);
            return null;
        }
    },

    async addPatient(patient) {
        try {
            const response = await fetch(`${this.baseUrl}/patients`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'add', ...patient })
            });
            return response.ok;
        } catch (e) {
            console.error('Error adding patient:', e);
            return false;
        }
    },

    // Doctors API
    async getDoctors() {
        try {
            const response = await fetch(`${this.baseUrl}/doctors`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'get_all' })
            });
            const data = await response.json();
            return data.doctors || [];
        } catch (e) {
            console.error('Error fetching doctors:', e);
            return [];
        }
    },

    async getDoctor(id) {
        try {
            const response = await fetch(`${this.baseUrl}/doctors`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'get', doctor_id: id })
            });
            const data = await response.json();
            return data.doctor || null;
        } catch (e) {
            console.error('Error fetching doctor:', e);
            return null;
        }
    },

    // Appointments API
    async getAppointments() {
        try {
            const response = await fetch(`${this.baseUrl}/appointments`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'get_all' })
            });
            const data = await response.json();
            return data.appointments || [];
        } catch (e) {
            console.error('Error fetching appointments:', e);
            return [];
        }
    },

    async getAppointmentsByDoctor(doctorId) {
        try {
            const response = await fetch(`${this.baseUrl}/appointments`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'get', filter_by: 'doctor_id', filter_value: doctorId })
            });
            const data = await response.json();
            return data.appointments || [];
        } catch (e) {
            console.error('Error fetching appointments:', e);
            return [];
        }
    },

    async getAppointmentsByPatient(patientId) {
        try {
            const response = await fetch(`${this.baseUrl}/appointments`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'get', filter_by: 'patient_id', filter_value: patientId })
            });
            const data = await response.json();
            return data.appointments || [];
        } catch (e) {
            console.error('Error fetching patient appointments:', e);
            return [];
        }
    },

    async addAppointment(appointment) {
        try {
            const response = await fetch(`${this.baseUrl}/appointments`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'add', ...appointment })
            });
            return response.ok;
        } catch (e) {
            console.error('Error adding appointment:', e);
            return false;
        }
    },

    // Attendance API
    async getAttendance(doctorId = null, date = null) {
        try {
            const response = await fetch(`${this.baseUrl}/attendance`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    action: doctorId ? 'get' : 'get_all',
                    doctor_id: doctorId,
                    date: date
                })
            });
            const data = await response.json();
            return data.attendance || [];
        } catch (e) {
            console.error('Error fetching attendance:', e);
            return [];
        }
    },

    async addAttendance(attendance) {
        try {
            const response = await fetch(`${this.baseUrl}/attendance`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'add', ...attendance })
            });
            return response.ok;
        } catch (e) {
            console.error('Error adding attendance:', e);
            return false;
        }
    },

    // Prescriptions API
    async getPrescriptions(patientId = null, doctorId = null) {
        try {
            const response = await fetch(`${this.baseUrl}/prescriptions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    action: patientId || doctorId ? 'get' : 'get_all',
                    patient_id: patientId,
                    doctor_id: doctorId
                })
            });
            const data = await response.json();
            return data.prescriptions || [];
        } catch (e) {
            console.error('Error fetching prescriptions:', e);
            return [];
        }
    },

    async addPrescription(prescription) {
        try {
            const response = await fetch(`${this.baseUrl}/prescriptions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'add', ...prescription })
            });
            return response.ok;
        } catch (e) {
            console.error('Error adding prescription:', e);
            return false;
        }
    },

    async getLabReports(patientId) {
        const response = await fetch(`${this.baseUrl}/lab-reports`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'get', patient_id: patientId })
        });
        const data = await response.json();
        return data.reports || [];
    },

    async addLabReport(report) {
        const response = await fetch(`${this.baseUrl}/lab-reports`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'add', ...report })
        });
        return response.ok;
    },

    async getReferrals(patientId) {
        const response = await fetch(`${this.baseUrl}/referrals`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'get', patient_id: patientId })
        });
        const data = await response.json();
        return data.referrals || [];
    },

    async addReferral(referral) {
        const response = await fetch(`${this.baseUrl}/referrals`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'add', ...referral })
        });
        return response.ok;
    }
};

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = API;
}
