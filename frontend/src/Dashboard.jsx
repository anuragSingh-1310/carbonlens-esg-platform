import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import {
  Database,
  Clock,
  AlertTriangle,
  CheckCircle,
  UploadCloud,
  Filter,
  ChevronLeft,
  ChevronRight,
  X,
  Edit2,
  Check,
  Flag,
  TrendingUp,
  RefreshCw,
  CornerDownRight,
  UserCheck
} from 'lucide-react';

// Setup base configuration for API. Customize this as per dev environment setup.
const API_BASE = 'https://carbonlens-esg-platform.onrender.com/api';

// Simple Authorization config mapping for multi-tenant simulation
const AXIOS_CONFIG = {
  headers: {
    'Authorization': 'Bearer demo-analyst-token' // In production, this token is retrieved from storage/auth contexts
  }
};

export default function Dashboard() {
  // --- STATE SYSTEM ---
  const [metrics, setMetrics] = useState({
    total_records: 0,
    pending_count: 0,
    flagged_count: 0,
    approved_count: 0,
    scope_distribution: { SCOPE_1: 0, SCOPE_2: 0, SCOPE_3: 0 }
  });
  const [jobs, setJobs] = useState([]);
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [jobsLoading, setJobsLoading] = useState(false);

  // Pagination & Filters
  const [page, setPage] = useState(1);
  const [hasNextPage, setHasNextPage] = useState(false);
  const [hasPrevPage, setHasPrevPage] = useState(false);
  const [filters, setFilters] = useState({
    review_status: '',
    scope: '',
    source_type: ''
  });

  // Selection
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [selectedRecord, setSelectedRecord] = useState(null);

  // Ingestion Upload
  const [uploadSource, setUploadSource] = useState('SAP_PROCUREMENT');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const fileInputRef = useRef(null);

  // Drawer Form Editing State
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    category: '',
    original_quantity: '',
    original_unit: '',
    transaction_date: '',
    plant_facility_code: '',
    anomaly_flag_reason: ''
  });

  // --- SMART OCR DOCUMENT INGESTION STATE ---
  const [activeTab, setActiveTab] = useState('smart');
  const [isOcrProcessing, setIsOcrProcessing] = useState(false);
  const [ocrStage, setOcrStage] = useState('');
  const [activeExtraction, setActiveExtraction] = useState(null);
  const [ocrError, setOcrError] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  // Mock Mode state - Activates if connection to real Django REST APIs fails
  const [isMockMode, setIsMockMode] = useState(false);

  // --- MOCK DATA FOR OUT-OF-THE-BOX MVP PRESENTATIONS ---
  const MOCK_METRICS = {
    total_records: 142,
    pending_count: 42,
    flagged_count: 15,
    approved_count: 85,
    scope_distribution: { SCOPE_1: 28400.5, SCOPE_2: 15200.0, SCOPE_3: 45900.2 }
  };

  const MOCK_JOBS = [
    { id: 1, source_type: 'SAP_PROCUREMENT', status: 'COMPLETED', created_at: '2026-05-24T22:15:00', metadata: { filename: 'sap_fuel_q2.csv', filesize_bytes: 4520 } },
    { id: 2, source_type: 'UTILITY_ELECTRICITY', status: 'COMPLETED', created_at: '2026-05-24T20:30:00', metadata: { filename: 'utility_h1_hq.csv', filesize_bytes: 1205 } },
    { id: 3, source_type: 'TRAVEL_API', status: 'COMPLETED', created_at: '2026-05-24T18:00:00', metadata: { filename: 'travel_q1_export.json', filesize_bytes: 8400 } },
    { id: 4, source_type: 'SAP_PROCUREMENT', status: 'FAILED', error_summary: 'Missing required columns: BUDAT', created_at: '2026-05-24T15:20:00', metadata: { filename: 'corrupted_sap.csv', filesize_bytes: 200 } }
  ];

  const MOCK_RECORDS = [
    {
      id: 101,
      scope: 'SCOPE_1',
      category: 'STATIONARY_FUEL',
      original_quantity: '25000.000000',
      original_unit: 'GAL',
      normalized_quantity: '94635.250000',
      normalized_unit: 'LITERS',
      transaction_date: '2026-05-15',
      plant_facility_code: 'PLANT_A',
      review_status: 'PENDING',
      anomaly_flag_reason: null,
      raw_row: {
        id: 501,
        row_index: 12,
        payload: { MATNR: 'HEAVY FUEL OIL - GENERATOR 1', MENG: '25000', MEINS: 'GAL', WERKS: 'PLANT_A', BUDAT: '20260515' }
      }
    },
    {
      id: 102,
      scope: 'SCOPE_2',
      category: 'PURCHASED_ELECTRICITY',
      original_quantity: '120500.000000',
      original_unit: 'kWh',
      normalized_quantity: '120500.000000',
      normalized_unit: 'kWh',
      transaction_date: '2026-04-30',
      plant_facility_code: 'ACCT-88402',
      review_status: 'FLAGGED',
      anomaly_flag_reason: 'Electricity consumption spike detected (120500 kWh) | Suspiciously high meter multiplier (105)',
      raw_row: {
        id: 502,
        row_index: 2,
        payload: { Account_Number: 'ACCT-88402', Start_Date: '2026-04-01', End_Date: '2026-04-30', Usage_kWh: '1147.61', Meter_Multiplier: '105' }
      }
    },
    {
      id: 103,
      scope: 'SCOPE_3',
      category: 'BUSINESS_TRAVEL',
      original_quantity: '6710.000000',
      original_unit: 'km',
      normalized_quantity: '10065.000000',
      normalized_unit: 'km-CO2e-factor',
      transaction_date: '2026-05-10',
      plant_facility_code: 'HQ_TRAVEL',
      review_status: 'APPROVED',
      approved_by_email: 'compliance.auditor@carbonlens.com',
      approved_at: '2026-05-24T22:30:00',
      anomaly_flag_reason: null,
      raw_row: {
        id: 503,
        row_index: 1,
        payload: { booking_id: 'BKG-9921', employee_email: 'executive@carbonlens.com', origin_airport: 'DEL', destination_airport: 'LHR', cabin_class: 'BUSINESS' }
      }
    }
  ];

  // --- API SERVICE CONNECTIVITY ---
  const fetchData = async () => {
    setLoading(true);
    try {
      // 1. Fetch Summary Cards Metrics
      const metricsResponse = await axios.get(`${API_BASE}/dashboard/metrics/`, AXIOS_CONFIG);
      setMetrics(metricsResponse.data);
      setIsMockMode(false);
    } catch (err) {
      console.warn("Django Server connection failed, falling back to rich static mock dashboard state.");
      setIsMockMode(true);
      setMetrics(MOCK_METRICS);
    }

    try {
      // 2. Fetch Activity Records
      let query = `?page=${page}`;
      if (filters.review_status) query += `&review_status=${filters.review_status}`;
      if (filters.scope) query += `&scope=${filters.scope}`;
      if (filters.source_type) query += `&source_type=${filters.source_type}`;

      if (isMockMode) {
        setRecords(MOCK_RECORDS);
        setHasNextPage(false);
        setHasPrevPage(false);
      } else {
        const recordsResponse = await axios.get(`${API_BASE}/records/${query}`, AXIOS_CONFIG);
        setRecords(recordsResponse.data.results || recordsResponse.data);
        setHasNextPage(!!recordsResponse.data.next);
        setHasPrevPage(!!recordsResponse.data.previous);
      }
    } catch (err) {
      setRecords(MOCK_RECORDS);
      setHasNextPage(false);
      setHasPrevPage(false);
    }
    setLoading(false);
  };

  const fetchJobs = async () => {
    setJobsLoading(true);
    try {
      if (isMockMode) {
        setJobs(MOCK_JOBS);
      } else {
        const jobsResponse = await axios.get(`${API_BASE}/ingestion/`, AXIOS_CONFIG);
        setJobs(jobsResponse.data);
      }
    } catch (err) {
      setJobs(MOCK_JOBS);
    }
    setJobsLoading(false);
  };

  // Run initial queries
  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, filters, isMockMode]);

  useEffect(() => {
    fetchJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isMockMode]);

  // --- UPLOAD HANDLER ---
  const handleUpload = async (e) => {
    e.preventDefault();
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      alert("Please select a file to upload first");
      return;
    }

    setIsUploading(true);
    setUploadProgress("Initiating upload...");

    const formData = new FormData();
    formData.append('file', file);
    formData.append('source_type', uploadSource);

    try {
      if (isMockMode) {
        // Simulate local ingest
        setUploadProgress("Simulating parser logic...");
        setTimeout(() => {
          setUploadProgress("");
          setIsUploading(false);
          alert("Mock upload processed. Fresh mock values loaded.");
          fetchData();
          fetchJobs();
        }, 1500);
      } else {
        setUploadProgress("Uploading file...");
        await axios.post(`${API_BASE}/ingestion/`, formData, {
          headers: {
            ...AXIOS_CONFIG.headers,
            'Content-Type': 'multipart/form-data'
          }
        });
        setUploadProgress("Data loaded successfully.");
        setTimeout(() => {
          setUploadProgress("");
          setIsUploading(false);
          fetchData();
          fetchJobs();
        }, 1000);
      }
    } catch (err) {
      console.error(err);
      setUploadProgress("");
      setIsUploading(false);
      alert(`Upload failed: ${err.response?.data?.file || err.message}`);
    }
  };

  // --- SMART OCR DOCUMENT UPLOAD & PARSING HANDLERS ---
  const handleDocumentUpload = async (file) => {
    if (!file) return;

    setIsOcrProcessing(true);
    setOcrError(null);
    setActiveExtraction(null);

    const stages = [
      "Scanning document structure...",
      "Performing OCR & text extraction...",
      "Classifying emission scope...",
      "Parsing carbon entities...",
      "Verifying database duplicates...",
      "Draft record created in ledger!"
    ];

    let stageIdx = 0;
    setOcrStage(stages[0]);
    const stageInterval = setInterval(() => {
      stageIdx++;
      if (stageIdx < stages.length - 1) {
        setOcrStage(stages[stageIdx]);
      }
    }, 450);

    const formData = new FormData();
    formData.append('file', file);

    try {
      if (isMockMode) {
        await new Promise(resolve => setTimeout(resolve, 2200));
        clearInterval(stageInterval);
        setOcrStage(stages[5]);

        const filenameLower = file.name.toLowerCase();
        let simulated = {
          record_id: 999 + Math.floor(Math.random() * 100),
          category: "STATIONARY_FUEL",
          original_quantity: 850.00,
          original_unit: "LITERS",
          normalized_quantity: 850.00,
          normalized_unit: "LITERS",
          transaction_date: new Date().toISOString().split('T')[0],
          plant_facility_code: "PLANT_B",
          vendor: "Shell Fuel Ltd.",
          invoice_amount: 1245.50,
          confidence_level: 0.94,
          scope_detected: "SCOPE_1",
          document_type: "fuel_invoice",
          warnings: []
        };

        if (filenameLower.includes("elect") || filenameLower.includes("utility") || filenameLower.includes("kwh") || filenameLower.includes("bill")) {
          simulated = {
            record_id: 999 + Math.floor(Math.random() * 100),
            category: "PURCHASED_ELECTRICITY",
            original_quantity: 14500.00,
            original_unit: "kWh",
            normalized_quantity: 14500.00,
            normalized_unit: "kWh",
            transaction_date: new Date().toISOString().split('T')[0],
            plant_facility_code: "ACCT-88904",
            vendor: "Electric Co.",
            invoice_amount: 2150.00,
            confidence_level: 0.97,
            scope_detected: "SCOPE_2",
            document_type: "electricity_bill",
            warnings: []
          };
        } else if (filenameLower.includes("travel") || filenameLower.includes("flight") || filenameLower.includes("receipt") || filenameLower.includes("air")) {
          simulated = {
            record_id: 999 + Math.floor(Math.random() * 100),
            category: "BUSINESS_TRAVEL",
            original_quantity: 1140.00,
            original_unit: "km",
            normalized_quantity: 1710.00,
            normalized_unit: "km-CO2e-factor",
            transaction_date: new Date().toISOString().split('T')[0],
            plant_facility_code: "HQ_TRAVEL",
            vendor: "British Airways",
            invoice_amount: 850.00,
            confidence_level: 0.91,
            scope_detected: "SCOPE_3",
            document_type: "travel_receipt",
            warnings: ["Airport route connection estimated automatically."]
          };
        }

        setTimeout(() => {
          setActiveExtraction(simulated);
          setIsOcrProcessing(false);
        }, 300);
      } else {
        const response = await axios.post(`${API_BASE}/upload-document/`, formData, {
          headers: {
            ...AXIOS_CONFIG.headers,
            'Content-Type': 'multipart/form-data'
          }
        });
        clearInterval(stageInterval);
        setOcrStage(stages[5]);
        
        const resData = response.data;
        const mapped = {
          record_id: resData.extracted_data.record_id,
          category: resData.extracted_data.category,
          original_quantity: resData.extracted_data.original_quantity,
          original_unit: resData.extracted_data.original_unit,
          normalized_quantity: resData.extracted_data.normalized_quantity,
          normalized_unit: resData.extracted_data.normalized_unit,
          transaction_date: resData.extracted_data.transaction_date,
          plant_facility_code: resData.extracted_data.plant_facility_code,
          vendor: resData.extracted_data.vendor,
          invoice_amount: resData.extracted_data.invoice_amount,
          confidence_level: resData.extracted_data.confidence_level,
          scope_detected: resData.scope_detected,
          document_type: resData.document_type,
          warnings: resData.warnings || []
        };
        
        setTimeout(() => {
          setActiveExtraction(mapped);
          setIsOcrProcessing(false);
          fetchData();
          fetchJobs();
        }, 300);
      }
    } catch (err) {
      clearInterval(stageInterval);
      setIsOcrProcessing(false);
      const errMsg = err.response?.data?.error || err.message;
      setOcrError(typeof errMsg === 'object' ? JSON.stringify(errMsg) : errMsg);
      console.error("OCR upload error:", err);
    }
  };

  const handleApproveExtraction = async (e) => {
    e.preventDefault();
    if (!activeExtraction) return;

    try {
      if (isMockMode) {
        const newRecord = {
          id: activeExtraction.record_id,
          scope: activeExtraction.scope_detected,
          category: activeExtraction.category,
          original_quantity: String(activeExtraction.original_quantity),
          original_unit: activeExtraction.original_unit,
          normalized_quantity: String(activeExtraction.normalized_quantity),
          normalized_unit: activeExtraction.normalized_unit,
          transaction_date: activeExtraction.transaction_date,
          plant_facility_code: activeExtraction.plant_facility_code,
          review_status: 'APPROVED',
          approved_by_email: 'compliance.auditor@carbonlens.com',
          approved_at: new Date().toISOString(),
          anomaly_flag_reason: null,
          raw_row: {
            id: 900 + Math.floor(Math.random() * 100),
            row_index: 1,
            payload: { ocr_vendor: activeExtraction.vendor, ocr_amount: activeExtraction.invoice_amount }
          }
        };

        setRecords(prev => [newRecord, ...prev]);
        setMetrics(prev => ({
          ...prev,
          total_records: prev.total_records + 1,
          approved_count: prev.approved_count + 1,
          scope_distribution: {
            ...prev.scope_distribution,
            [activeExtraction.scope_detected]: (prev.scope_distribution[activeExtraction.scope_detected] || 0) + Number(activeExtraction.normalized_quantity)
          }
        }));

        setActiveExtraction(null);
        alert("Smart document record approved and registered successfully!");
      } else {
        await axios.patch(`${API_BASE}/records/${activeExtraction.record_id}/review/`, {
          category: activeExtraction.category,
          original_quantity: activeExtraction.original_quantity,
          original_unit: activeExtraction.original_unit,
          transaction_date: activeExtraction.transaction_date,
          plant_facility_code: activeExtraction.plant_facility_code,
          review_status: 'APPROVED'
        }, AXIOS_CONFIG);

        setActiveExtraction(null);
        fetchData();
        fetchJobs();
        alert("Smart document successfully audited and approved!");
      }
    } catch (err) {
      alert(`Approve failed: ${err.response?.data?.[0] || err.message}`);
    }
  };

  // --- WORKFLOW SIGN-OFFS & EDITS ---
  const handleReviewAction = async (recordId, newStatus, reason = null) => {
    try {
      const payload = { review_status: newStatus };
      if (reason !== null) {
        payload.anomaly_flag_reason = reason;
      }

      if (isMockMode) {
        // Local mockup state update
        setRecords(prev => prev.map(rec => {
          if (rec.id === recordId) {
            return {
              ...rec,
              review_status: newStatus,
              anomaly_flag_reason: reason || rec.anomaly_flag_reason,
              approved_by_email: newStatus === 'APPROVED' ? 'auditor.demo@carbonlens.com' : null,
              approved_at: newStatus === 'APPROVED' ? new Date().toISOString() : null
            };
          }
          return rec;
        }));

        // Update metrics representation
        setMetrics(prev => ({
          ...prev,
          pending_count: Math.max(0, prev.pending_count - (newStatus === 'APPROVED' || newStatus === 'FLAGGED' ? 1 : 0)),
          approved_count: prev.approved_count + (newStatus === 'APPROVED' ? 1 : 0),
          flagged_count: prev.flagged_count + (newStatus === 'FLAGGED' ? 1 : 0)
        }));

        if (selectedRecord && selectedRecord.id === recordId) {
          setSelectedRecord(prev => ({
            ...prev,
            review_status: newStatus,
            anomaly_flag_reason: reason || prev.anomaly_flag_reason
          }));
        }
      } else {
        const response = await axios.patch(
          `${API_BASE}/records/${recordId}/review/`,
          payload,
          AXIOS_CONFIG
        );
        setSelectedRecord(response.data);
        fetchData();
      }
    } catch (err) {
      alert(`Review action failed: ${err.response?.data?.[0] || err.message}`);
    }
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    if (!selectedRecord) return;

    try {
      if (isMockMode) {
        setRecords(prev => prev.map(rec => {
          if (rec.id === selectedRecord.id) {
            const updated = {
              ...rec,
              category: editForm.category,
              original_quantity: editForm.original_quantity,
              original_unit: editForm.original_unit,
              transaction_date: editForm.transaction_date,
              plant_facility_code: editForm.plant_facility_code
            };
            setSelectedRecord(updated);
            return updated;
          }
          return rec;
        }));
        setIsEditing(false);
      } else {
        const response = await axios.patch(
          `${API_BASE}/records/${selectedRecord.id}/review/`,
          editForm,
          AXIOS_CONFIG
        );
        setSelectedRecord(response.data);
        setIsEditing(false);
        fetchData();
      }
    } catch (err) {
      alert(`Editing record failed: ${err.response?.data?.[0] || err.message}`);
    }
  };

  // --- BULK ACTION WORKFLOWS ---
  const handleToggleSelectAll = () => {
    if (selectedIds.size === records.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(records.map(r => r.id)));
    }
  };

  const handleToggleSelectRow = (id) => {
    const updated = new Set(selectedIds);
    if (updated.has(id)) {
      updated.delete(id);
    } else {
      updated.add(id);
    }
    setSelectedIds(updated);
  };

  const handleBulkApprove = async () => {
    if (selectedIds.size === 0) return;
    const confirmApprove = window.confirm(`Are you sure you want to approve all ${selectedIds.size} selected records?`);
    if (!confirmApprove) return;

    setLoading(true);
    const idsToProcess = Array.from(selectedIds);

    try {
      if (isMockMode) {
        setRecords(prev => prev.map(rec => {
          if (selectedIds.has(rec.id)) {
            return {
              ...rec,
              review_status: 'APPROVED',
              approved_by_email: 'bulk.auditor@carbonlens.com',
              approved_at: new Date().toISOString()
            };
          }
          return rec;
        }));
        setSelectedIds(new Set());
        alert("Bulk approval executed.");
      } else {
        // Execute concurrent approvals using views logic
        await Promise.all(idsToProcess.map(id =>
          axios.patch(
            `${API_BASE}/records/${id}/review/`,
            { review_status: 'APPROVED' },
            AXIOS_CONFIG
          )
        ));
        setSelectedIds(new Set());
        fetchData();
        alert("Bulk approvals successfully synced with Django.");
      }
    } catch (err) {
      alert(`Bulk approval failed during operations: ${err.message}`);
    }
    setLoading(false);
  };

  // Helper calculation for scope percentages
  const getScopeShares = () => {
    const scope1 = Number(metrics.scope_distribution?.SCOPE_1 || 0);
    const scope2 = Number(metrics.scope_distribution?.SCOPE_2 || 0);
    const scope3 = Number(metrics.scope_distribution?.SCOPE_3 || 0);
    const sum = scope1 + scope2 + scope3 || 1;
    return {
      SCOPE_1: { val: scope1, pct: Math.round((scope1 / sum) * 100) },
      SCOPE_2: { val: scope2, pct: Math.round((scope2 / sum) * 100) },
      SCOPE_3: { val: scope3, pct: Math.round((scope3 / sum) * 100) },
    };
  };
  const scopeShares = getScopeShares();

  // Load selected record into active editor form on click
  const handleOpenDrawer = (record) => {
    setSelectedRecord(record);
    setIsEditing(false);
    setEditForm({
      category: record.category,
      original_quantity: record.original_quantity,
      original_unit: record.original_unit,
      transaction_date: record.transaction_date,
      plant_facility_code: record.plant_facility_code,
      anomaly_flag_reason: record.anomaly_flag_reason || ''
    });
  };

  return (
    <div className="min-h-screen bg-transparent text-slate-100 flex flex-col font-sans relative overflow-hidden">
      {/* Dynamic ambient HSL lights mimicking Antigravity IDE theme */}
      <div className="glow-spot-teal top-[-10%] left-[-10%]" />
      <div className="glow-spot-blue bottom-[-10%] right-[-10%]" />

      {/* HEADER WIDGET */}
      <header className="glass-header px-6 py-4 flex items-center justify-between sticky top-0 z-40">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-[#073642] flex items-center justify-center shadow-md">
            <TrendingUp className="h-5 w-5 text-[#FAF5EB]" />
          </div>
          <div>
            <h1 className="font-extrabold text-lg tracking-wide text-white">CarbonLens</h1>
            <p className="text-[10px] uppercase tracking-widest text-[#586E75] font-bold">Enterprise ESG Ingestion & Audit</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Mock Mode banner */}
          <div className={`text-xs px-3 py-1.5 rounded-full flex items-center gap-2 border ${isMockMode
              ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
              : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
            }`}>
            <span className={`h-2 w-2 rounded-full ${isMockMode ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'}`} />
            {isMockMode ? 'Mock Server Sandbox' : 'Connected to Django API'}
          </div>

          <button
            onClick={() => setIsMockMode(!isMockMode)}
            className="text-xs bg-[#EEE8D5] hover:bg-[#E4DBBF] px-3 py-2 rounded-lg border border-slate-300/80 transition flex items-center gap-1.5 text-[#073642] font-semibold"
          >
            <RefreshCw className="h-3 w-3 text-[#073642]" />
            Switch Mode
          </button>

          <div className="h-8 w-px bg-slate-800" />

          <div className="text-right">
            <p className="text-sm font-semibold text-slate-200">System Auditor</p>
            <p className="text-xs text-slate-400">HQ Audit Division</p>
          </div>
        </div>
      </header>

      <main className="flex-1 p-6 space-y-6 max-w-7xl mx-auto w-full">

        {/* ROW 1: METRICS AND SCOPE DISTRIBUTIONS */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Metrics summary cards */}
          <div className="lg:col-span-2 grid grid-cols-2 gap-4">
            <div className="glass-card glow-teal p-5 flex items-center justify-between">
              <div>
                <p className="text-[10px] text-slate-400 uppercase tracking-widest font-bold">Total Ingested</p>
                <p className="text-3xl font-extrabold mt-2 text-white">{metrics.total_records}</p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-[#10b981]/10 flex items-center justify-center text-emerald-400 border border-[#10b981]/20 shadow-[0_0_15px_rgba(16,185,129,0.1)]">
                <Database className="h-6 w-6" />
              </div>
            </div>

            <div className="glass-card glow-blue p-5 flex items-center justify-between">
              <div>
                <p className="text-[10px] text-slate-400 uppercase tracking-widest font-bold">Pending Audits</p>
                <p className="text-3xl font-extrabold mt-2 text-white">{metrics.pending_count}</p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-[#3b82f6]/10 flex items-center justify-center text-blue-400 border border-[#3b82f6]/20 shadow-[0_0_15px_rgba(59,130,246,0.1)]">
                <Clock className="h-6 w-6 animate-pulse" />
              </div>
            </div>

            <div className={`glass-card glow-amber p-5 flex items-center justify-between ${metrics.flagged_count > 0 ? 'animate-anomaly-pulse border-amber-500/40 bg-amber-500/5' : ''
              }`}>
              <div>
                <p className="text-[10px] text-slate-400 uppercase tracking-widest font-bold">Flagged Anomalies</p>
                <p className="text-3xl font-extrabold mt-2 text-white">{metrics.flagged_count}</p>
              </div>
              <div className={`h-12 w-12 rounded-xl bg-[#f59e0b]/10 flex items-center justify-center text-amber-500 border border-[#f59e0b]/20 shadow-[0_0_15px_rgba(245,158,11,0.1)] ${metrics.flagged_count > 0 ? 'animate-bounce' : ''
                }`}>
                <AlertTriangle className="h-6 w-6" />
              </div>
            </div>

            <div className="glass-card glow-purple p-5 flex items-center justify-between">
              <div>
                <p className="text-[10px] text-slate-400 uppercase tracking-widest font-bold">Approved Audits</p>
                <p className="text-3xl font-extrabold mt-2 text-white">{metrics.approved_count}</p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-[#a78bfa]/10 flex items-center justify-center text-[#c084fc] border border-[#a78bfa]/20 shadow-[0_0_15px_rgba(167,139,250,0.1)]">
                <CheckCircle className="h-6 w-6" />
              </div>
            </div>
          </div>

          {/* Scope Distribution Bar Graph Panel */}
          <div className="glass-card glow-purple p-5 space-y-4">
            <h3 className="text-sm font-semibold tracking-wider text-slate-300">Normalized Emissions Shares</h3>

            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-400">Scope 1 (Direct Combustions)</span>
                  <span className="font-semibold text-white">{scopeShares.SCOPE_1.pct}% ({scopeShares.SCOPE_1.val.toLocaleString()} L)</span>
                </div>
                <div className="h-2 bg-white border border-slate-300/40 rounded-full overflow-hidden">
                  <div className="h-full bg-[#073642] rounded-full" style={{ width: `${scopeShares.SCOPE_1.pct}%` }} />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-400">Scope 2 (Electricity/Grid)</span>
                  <span className="font-semibold text-white">{scopeShares.SCOPE_2.pct}% ({scopeShares.SCOPE_2.val.toLocaleString()} kWh)</span>
                </div>
                <div className="h-2 bg-white border border-slate-300/40 rounded-full overflow-hidden">
                  <div className="h-full bg-[#073642] rounded-full" style={{ width: `${scopeShares.SCOPE_2.pct}%` }} />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-400">Scope 3 (Travel & Value Chain)</span>
                  <span className="font-semibold text-white">{scopeShares.SCOPE_3.pct}% ({scopeShares.SCOPE_3.val.toLocaleString()} km-CO2e)</span>
                </div>
                <div className="h-2 bg-white border border-slate-300/40 rounded-full overflow-hidden">
                  <div className="h-full bg-[#073642] rounded-full" style={{ width: `${scopeShares.SCOPE_3.pct}%` }} />
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ROW 2: SPLIT INGESTION AND JOB HISTORY */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* File Upload card */}
          <div className="glass-card glow-teal p-5 space-y-4 flex flex-col justify-between">
            {/* Conditional Render: Active extraction editor takes over card to ensure focused auditing workflow */}
            {activeExtraction ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between border-b border-slate-850 pb-2">
                  <div>
                    <h3 className="font-extrabold text-sm text-slate-100 flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                      Smart Verification
                    </h3>
                    <p className="text-[10px] text-slate-400">Review & verify AI-extracted metrics before final ingestion.</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveExtraction(null)}
                    className="text-slate-400 hover:text-white p-1 hover:bg-slate-850 rounded-lg transition"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                {/* Extraction confidence badge & bar */}
                <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-850 flex items-center justify-between">
                  <div className="space-y-0.5">
                    <p className="text-[9px] uppercase tracking-wider text-slate-500 font-bold">Extraction Confidence</p>
                    <div className="flex items-center gap-1.5">
                      <span className={`text-base font-extrabold ${
                        activeExtraction.confidence_level > 0.85 ? 'text-emerald-400' :
                        activeExtraction.confidence_level > 0.70 ? 'text-amber-400' : 'text-red-400'
                      }`}>
                        {Math.round(activeExtraction.confidence_level * 100)}%
                      </span>
                      <span className="text-[9px] text-slate-400 font-medium">
                        ({activeExtraction.confidence_level > 0.85 ? 'High Precision' : 'Requires Review'})
                      </span>
                    </div>
                  </div>
                  <div className="h-9 w-9 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-400 border border-emerald-500/20 shadow-[0_0_10px_rgba(16,185,129,0.1)]">
                    <CheckCircle className="h-5 w-5" />
                  </div>
                </div>

                {/* Warnings / Low quality alarms */}
                {activeExtraction.warnings && activeExtraction.warnings.length > 0 && (
                  <div className="p-3 rounded-xl bg-amber-500/5 border border-amber-500/20 text-[10px] text-amber-400 space-y-1">
                    <div className="flex items-center gap-1 font-bold">
                      <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
                      <span>Extraction Warnings</span>
                    </div>
                    <ul className="list-disc pl-4 space-y-0.5 text-[9px] text-amber-300/80 font-mono leading-relaxed">
                      {activeExtraction.warnings.map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                  </div>
                )}

                {/* Dynamic verification form */}
                <form onSubmit={handleApproveExtraction} className="space-y-3.5 text-xs">
                  <div className="grid grid-cols-2 gap-2.5">
                    <div>
                      <label className="text-[9px] text-slate-400 block mb-1 font-bold uppercase tracking-wider">Vendor/Supplier</label>
                      <input
                        type="text"
                        value={activeExtraction.vendor}
                        onChange={(e) => setActiveExtraction({ ...activeExtraction, vendor: e.target.value })}
                        className="w-full glass-input text-slate-200 border border-slate-800 text-[11px] p-2 rounded-lg focus:outline-none focus:border-emerald-500 font-semibold"
                      />
                    </div>
                    <div>
                      <label className="text-[9px] text-slate-400 block mb-1 font-bold uppercase tracking-wider">Plant / Facility</label>
                      <input
                        type="text"
                        value={activeExtraction.plant_facility_code}
                        onChange={(e) => setActiveExtraction({ ...activeExtraction, plant_facility_code: e.target.value })}
                        className="w-full glass-input text-slate-200 border border-slate-800 text-[11px] p-2 rounded-lg focus:outline-none focus:border-emerald-500 font-mono"
                      />
                    </div>
                    <div>
                      <label className="text-[9px] text-slate-400 block mb-1 font-bold uppercase tracking-wider">Quantity</label>
                      <input
                        type="text"
                        value={activeExtraction.original_quantity}
                        onChange={(e) => setActiveExtraction({ ...activeExtraction, original_quantity: e.target.value, normalized_quantity: e.target.value })}
                        className="w-full glass-input text-slate-200 border border-slate-800 text-[11px] p-2 rounded-lg focus:outline-none focus:border-emerald-500 font-mono font-bold"
                      />
                    </div>
                    <div>
                      <label className="text-[9px] text-slate-400 block mb-1 font-bold uppercase tracking-wider">Original Unit</label>
                      <input
                        type="text"
                        value={activeExtraction.original_unit}
                        onChange={(e) => setActiveExtraction({ ...activeExtraction, original_unit: e.target.value })}
                        className="w-full glass-input text-slate-200 border border-slate-800 text-[11px] p-2 rounded-lg focus:outline-none focus:border-emerald-500"
                      />
                    </div>
                    <div>
                      <label className="text-[9px] text-slate-400 block mb-1 font-bold uppercase tracking-wider">Invoice Date</label>
                      <input
                        type="date"
                        value={activeExtraction.transaction_date}
                        onChange={(e) => setActiveExtraction({ ...activeExtraction, transaction_date: e.target.value })}
                        className="w-full glass-input text-slate-200 border border-slate-800 text-[11px] p-2 rounded-lg focus:outline-none focus:border-emerald-500 font-mono"
                      />
                    </div>
                    <div>
                      <label className="text-[9px] text-slate-400 block mb-1 font-bold uppercase tracking-wider">Invoice Amount ($)</label>
                      <input
                        type="text"
                        value={activeExtraction.invoice_amount}
                        onChange={(e) => setActiveExtraction({ ...activeExtraction, invoice_amount: e.target.value })}
                        className="w-full glass-input text-slate-200 border border-slate-800 text-[11px] p-2 rounded-lg focus:outline-none focus:border-emerald-500 font-mono font-semibold"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="text-[9px] text-slate-400 block mb-1 font-bold uppercase tracking-wider">ESG Activity Type / Scope</label>
                    <select
                      value={activeExtraction.category}
                      onChange={(e) => {
                        const cat = e.target.value;
                        let scope = "SCOPE_3";
                        if (cat === "STATIONARY_FUEL") scope = "SCOPE_1";
                        if (cat === "PURCHASED_ELECTRICITY") scope = "SCOPE_2";
                        setActiveExtraction({ ...activeExtraction, category: cat, scope_detected: scope });
                      }}
                      className="w-full glass-input text-slate-200 border border-slate-800 text-[11px] p-2 rounded-lg focus:outline-none focus:border-emerald-500 font-semibold"
                    >
                      <option value="PURCHASED_ELECTRICITY">Scope 2 - Purchased Electricity</option>
                      <option value="STATIONARY_FUEL">Scope 1 - Stationary Combustion</option>
                      <option value="BUSINESS_TRAVEL">Scope 3 - Business Travel</option>
                      <option value="SUPPLIER_TRANSPORT">Scope 3 - Supplier Transportation</option>
                      <option value="PURCHASED_GOODS">Scope 3 - Purchased Goods</option>
                    </select>
                  </div>

                  <div className="flex gap-2.5 pt-3 border-t border-slate-850">
                    <button
                      type="submit"
                      className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white font-extrabold py-2.5 rounded-xl text-xs transition flex items-center justify-center gap-1.5 shadow-[0_4px_12px_rgba(16,185,129,0.15)] hover:translate-y-[-1px]"
                    >
                      <CheckCircle className="h-4 w-4" />
                      Approve & Ingest
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setActiveExtraction(null);
                        fetchData();
                        fetchJobs();
                        alert("Draft ingestion record saved as PENDING in the ledger.");
                      }}
                      className="flex-1 bg-slate-850 hover:bg-slate-800 text-slate-300 font-bold py-2.5 rounded-xl text-xs transition flex items-center justify-center gap-1.5 border border-slate-880 hover:text-slate-100"
                    >
                      Keep as Draft
                    </button>
                  </div>
                </form>
              </div>
            ) : (
              // Standard Upload View with tab switcher
              <div className="space-y-4">
                <div>
                  <h3 className="font-bold text-sm text-slate-200">ESG Ingestion Portal</h3>
                  <p className="text-xs text-slate-400">Import business files into the multi-tenant engine.</p>
                </div>

                {/* Tab Switcher */}
                <div className="flex border-b border-slate-800 pb-1 mb-1">
                  <button
                    type="button"
                    onClick={() => { setActiveTab('smart'); setOcrError(null); }}
                    className={`flex-1 text-[11px] font-bold py-2 px-1 rounded-t-lg transition flex items-center justify-center gap-1.5 ${
                      activeTab === 'smart' 
                        ? 'text-emerald-400 border-b-2 border-emerald-500 bg-emerald-500/5'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Database className="h-3.5 w-3.5" />
                    Smart OCR Invoice
                  </button>
                  <button
                    type="button"
                    onClick={() => { setActiveTab('csv'); }}
                    className={`flex-1 text-[11px] font-bold py-2 px-1 rounded-t-lg transition flex items-center justify-center gap-1.5 ${
                      activeTab === 'csv' 
                        ? 'text-emerald-400 border-b-2 border-emerald-500 bg-emerald-500/5'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <UploadCloud className="h-3.5 w-3.5" />
                    CSV / JSON Batch
                  </button>
                </div>

                {activeTab === 'smart' ? (
                  /* SMART OCR INGESTION FORM */
                  <div className="space-y-4">
                    {isOcrProcessing ? (
                      <div className="p-6 rounded-xl bg-slate-950/60 border border-slate-850 flex flex-col items-center justify-center gap-3 text-center min-h-[160px] animate-pulse">
                        <div className="relative flex items-center justify-center">
                          <div className="h-10 w-10 rounded-full border-2 border-slate-800 border-t-emerald-400 animate-spin" />
                          <Database className="h-4.5 w-4.5 text-emerald-400 absolute" />
                        </div>
                        <div className="space-y-1">
                          <p className="text-xs text-emerald-400 font-mono font-bold uppercase tracking-wider">{ocrStage}</p>
                          <p className="text-[10px] text-slate-500">Extracting ESG targets using character vision pipeline</p>
                        </div>
                      </div>
                    ) : ocrError ? (
                      <div className="p-4 rounded-xl bg-red-500/5 border border-red-500/20 text-xs text-red-400 space-y-3 min-h-[160px] flex flex-col justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5 font-bold">
                            <AlertTriangle className="h-4.5 w-4.5 text-red-400" />
                            <span>OCR Pipeline Failure</span>
                          </div>
                          <p className="font-mono text-[9px] bg-red-500/10 p-2 rounded leading-relaxed overflow-y-auto max-h-[80px] break-all">{ocrError}</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => setOcrError(null)}
                          className="w-full text-center py-2 rounded-lg bg-red-500/10 hover:bg-red-500/20 transition font-bold text-[10px]"
                        >
                          Clear & Retry Upload
                        </button>
                      </div>
                    ) : (
                      <div
                        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                        onDragLeave={() => setDragOver(false)}
                        onDrop={(e) => {
                          e.preventDefault();
                          setDragOver(false);
                          const file = e.dataTransfer?.files?.[0];
                          if (file) handleDocumentUpload(file);
                        }}
                        onClick={() => {
                          const fileInput = document.getElementById('ocr-file-input');
                          fileInput?.click();
                        }}
                        className={`border border-dashed rounded-xl py-9 flex flex-col items-center justify-center cursor-pointer transition ${
                          dragOver 
                            ? 'border-emerald-400 bg-emerald-950/20 text-emerald-400 scale-[1.01]' 
                            : 'border-slate-800 hover:border-emerald-500/80 bg-slate-950/30 hover:bg-slate-950/50'
                        } group relative overflow-hidden`}
                      >
                        <UploadCloud className={`h-10 w-10 mb-2 transition ${dragOver ? 'text-emerald-400 animate-bounce' : 'text-slate-500 group-hover:text-emerald-400'}`} />
                        <span className="text-xs text-slate-300 font-bold">Drag & Drop Invoice / Bill</span>
                        <span className="text-[10px] text-slate-500 mt-1">Supports PDF, PNG, JPG, JPEG</span>
                        <span className="text-[8px] uppercase tracking-widest text-emerald-500/70 font-mono mt-1.5 font-bold">OCR-Powered Vision Pipeline</span>
                        <input
                          id="ocr-file-input"
                          type="file"
                          accept=".pdf,.png,.jpg,.jpeg"
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) handleDocumentUpload(file);
                          }}
                          className="hidden"
                        />
                      </div>
                    )}
                  </div>
                ) : (
                  /* LEGACY CSV / JSON BATCH FORM */
                  <form onSubmit={handleUpload} className="space-y-4">
                    <div>
                      <label className="text-[10px] text-slate-400 block mb-1 font-bold uppercase tracking-wider">Ingestion Source Type</label>
                      <select
                        value={uploadSource}
                        onChange={(e) => setUploadSource(e.target.value)}
                        className="w-full glass-input text-slate-100 border border-slate-800/80 text-xs p-2.5 rounded-lg focus:outline-none focus:border-emerald-500 font-semibold"
                      >
                        <option value="SAP_PROCUREMENT">SAP Procurement / Fuel CSV</option>
                        <option value="UTILITY_ELECTRICITY">Utility Electricity CSV</option>
                        <option value="TRAVEL_API">Corporate Travel JSON Payload</option>
                      </select>
                    </div>

                    <div
                      onClick={() => fileInputRef.current?.click()}
                      className="border border-dashed border-slate-800 hover:border-emerald-400/85 rounded-xl py-6 flex flex-col items-center justify-center cursor-pointer transition bg-slate-950/30 hover:bg-slate-950/50 group"
                    >
                      <UploadCloud className="h-8 w-8 text-slate-500 group-hover:text-emerald-400 mb-2 transition" />
                      <span className="text-xs text-slate-300 font-medium">Click to select files</span>
                      <span className="text-[10px] text-slate-500 mt-1">Supports CSV, JSON</span>
                      <input
                        type="file"
                        ref={fileInputRef}
                        onChange={(e) => {
                          if (e.target.files?.[0]) {
                            setUploadProgress(`Selected: ${e.target.files[0].name}`);
                          }
                        }}
                        className="hidden"
                      />
                    </div>

                    {uploadProgress && (
                      <div className="p-2.5 rounded-lg bg-slate-950 text-[10px] flex items-center gap-2 border border-slate-800 text-emerald-400 font-mono">
                        <CornerDownRight className="h-3 w-3" />
                        {uploadProgress}
                      </div>
                    )}

                    <button
                      type="submit"
                      disabled={isUploading}
                      className="w-full bg-[#073642] hover:bg-[#0c4452] text-[#FAF5EB] font-bold py-3 rounded-xl text-xs transition flex items-center justify-center gap-1.5 shadow-[0_4px_12px_rgba(7,54,66,0.15)] hover:shadow-[0_6px_20px_rgba(7,54,66,0.25)] hover:translate-y-[-1px] disabled:opacity-50"
                    >
                      {isUploading ? 'Executing Ingestion Services...' : 'Process Ingestion Job'}
                    </button>
                  </form>
                )}
              </div>
            )}
          </div>

          {/* Job Ingestion History Card */}
          <div className="glass-card glow-blue p-5 space-y-4 lg:col-span-2 flex flex-col">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-sm text-slate-200">Raw Ingestion Job History</h3>
                <p className="text-xs text-slate-400">Trace records generated by active import batches.</p>
              </div>
              <button
                onClick={fetchJobs}
                className="text-xs text-slate-400 hover:text-white flex items-center gap-1"
              >
                <RefreshCw className={`h-3 w-3 ${jobsLoading ? 'animate-spin' : ''}`} />
                Reload
              </button>
            </div>

            <div className="flex-1 overflow-y-auto max-h-[220px] space-y-2.5 pr-1">
              {jobs.map((job) => (
                <div key={job.id} className="glass-input p-3 rounded-lg border border-slate-850 flex items-center justify-between text-xs hover:border-slate-800 transition">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-200">{job.source_type}</span>
                      <span className="text-[10px] text-slate-500">| ID: {job.id}</span>
                      {job.metadata?.filename && (
                        <span className="text-[10px] bg-slate-850 px-1.5 py-0.5 rounded text-slate-400 font-mono">
                          {job.metadata.filename}
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-400">
                      {new Date(job.created_at).toLocaleString()}
                    </div>
                    {job.error_summary && (
                      <p className="text-[10px] text-red-400 font-mono bg-red-500/5 px-2 py-1 rounded border border-red-500/10 mt-1">
                        {job.error_summary}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-3">
                    <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold ${job.status === 'COMPLETED'
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        : job.status === 'FAILED'
                          ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                          : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                      }`}>
                      {job.status}
                    </span>
                  </div>
                </div>
              ))}

              {jobs.length === 0 && (
                <div className="h-full flex items-center justify-center text-slate-500 text-xs py-10">
                  No historical ingestion batches found.
                </div>
              )}
            </div>
          </div>
        </section>

        {/* ROW 3: MAIN ACTIVITY RECORDS TABLE */}
        <section className="glass-card glow-blue p-5 space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-850 pb-4">
            <div>
              <h3 className="font-bold text-sm text-slate-200">ESG Emissions Ledger</h3>
              <p className="text-xs text-slate-400">Analysts sign-off checklist and audit data table.</p>
            </div>

            {/* Filtering bar */}
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2 bg-[#EEE8D5] px-3 py-1.5 rounded-lg border border-slate-300/80 text-xs text-[#073642] font-semibold">
                <Filter className="h-3.5 w-3.5 text-[#073642]" />
                <span>Filters</span>
              </div>

              <select
                value={filters.review_status}
                onChange={(e) => setFilters({ ...filters, review_status: e.target.value })}
                className="glass-input text-slate-200 border border-slate-800 text-xs p-2 rounded-lg focus:outline-none focus:border-emerald-500"
              >
                <option value="">All Review Statuses</option>
                <option value="PENDING">Pending Review</option>
                <option value="FLAGGED">Flagged Anomalies</option>
                <option value="APPROVED">Approved Records</option>
              </select>

              <select
                value={filters.scope}
                onChange={(e) => setFilters({ ...filters, scope: e.target.value })}
                className="glass-input text-slate-200 border border-slate-800 text-xs p-2 rounded-lg focus:outline-none focus:border-emerald-500"
              >
                <option value="">All Scopes</option>
                <option value="SCOPE_1">Scope 1</option>
                <option value="SCOPE_2">Scope 2</option>
                <option value="SCOPE_3">Scope 3</option>
              </select>

              {/* Bulk Actions Button */}
              {selectedIds.size > 0 && (
                <button
                  onClick={handleBulkApprove}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition flex items-center gap-1"
                >
                  <UserCheck className="h-3.5 w-3.5" />
                  Bulk Approve ({selectedIds.size})
                </button>
              )}
            </div>
          </div>

          {/* TABLE CONTAINER */}
          <div className="overflow-x-auto rounded-lg border border-slate-850">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-950/80 text-slate-400 font-semibold border-b border-slate-850 uppercase tracking-wider">
                  <th className="py-3 px-4 w-10">
                    <input
                      type="checkbox"
                      checked={records.length > 0 && selectedIds.size === records.length}
                      onChange={handleToggleSelectAll}
                      className="rounded bg-slate-900 border-slate-800 text-emerald-500 focus:ring-0 cursor-pointer"
                    />
                  </th>
                  <th className="py-3 px-4">Category</th>
                  <th className="py-3 px-4">Scope</th>
                  <th className="py-3 px-4">Original Qty</th>
                  <th className="py-3 px-4">Normalized Qty</th>
                  <th className="py-3 px-4">Facility Code</th>
                  <th className="py-3 px-4">Transaction Date</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-center">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-850/80 bg-slate-900/10">
                {records.map((rec) => (
                  <tr
                    key={rec.id}
                    className={`hover:bg-slate-850/40 transition cursor-pointer ${selectedRecord?.id === rec.id ? 'bg-slate-850/30 border-l-2 border-emerald-500' : ''
                      }`}
                  >
                    <td className="py-3 px-4" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(rec.id)}
                        onChange={() => handleToggleSelectRow(rec.id)}
                        className="rounded bg-slate-900 border-slate-800 text-emerald-500 focus:ring-0 cursor-pointer"
                      />
                    </td>
                    <td className="py-3 px-4 font-semibold text-slate-200" onClick={() => handleOpenDrawer(rec)}>
                      {rec.category}
                    </td>
                    <td className="py-3 px-4" onClick={() => handleOpenDrawer(rec)}>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${rec.scope === 'SCOPE_1' ? 'bg-cyan-500/10 text-cyan-400' :
                          rec.scope === 'SCOPE_2' ? 'bg-yellow-500/10 text-yellow-400' :
                            'bg-purple-500/10 text-purple-400'
                        }`}>
                        {rec.scope}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-300" onClick={() => handleOpenDrawer(rec)}>
                      {Number(rec.original_quantity).toFixed(2)} {rec.original_unit}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-200 font-bold" onClick={() => handleOpenDrawer(rec)}>
                      {Number(rec.normalized_quantity).toFixed(2)} {rec.normalized_unit}
                    </td>
                    <td className="py-3 px-4 text-slate-400 font-mono" onClick={() => handleOpenDrawer(rec)}>
                      {rec.plant_facility_code}
                    </td>
                    <td className="py-3 px-4 text-slate-400 font-mono" onClick={() => handleOpenDrawer(rec)}>
                      {rec.transaction_date}
                    </td>
                    <td className="py-3 px-4" onClick={() => handleOpenDrawer(rec)}>
                      <div className="flex items-center gap-1.5">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${rec.review_status === 'APPROVED'
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                            : rec.review_status === 'FLAGGED'
                              ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                              : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                          }`}>
                          {rec.review_status}
                        </span>
                        {rec.anomaly_flag_reason && (
                          <AlertTriangle className="h-3.5 w-3.5 text-amber-500 animate-pulse" title={rec.anomaly_flag_reason} />
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-center" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => handleOpenDrawer(rec)}
                        className="text-slate-500 hover:text-emerald-500 font-bold px-3 py-1.5 rounded-lg glass-input hover:bg-white transition"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}

                {records.length === 0 && (
                  <tr>
                    <td colSpan="9" className="text-center py-10 text-slate-500">
                      {loading ? 'Querying records database...' : 'No activity records found matching filters.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* PAGINATION PANEL */}
          <div className="flex items-center justify-between text-xs pt-2">
            <span className="text-slate-400">
              Page <span className="font-semibold text-slate-200">{page}</span> of ESG emissions ledger
            </span>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1 || !hasPrevPage}
                className="glass-input hover:bg-white border border-slate-850/80 px-3 py-1.5 rounded-lg disabled:opacity-40 transition flex items-center gap-1 font-semibold"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Previous
              </button>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={!hasNextPage}
                className="glass-input hover:bg-white border border-slate-850/80 px-3 py-1.5 rounded-lg disabled:opacity-40 transition flex items-center gap-1 font-semibold"
              >
                Next
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </section>
      </main>

      {/* SLIDE-OUT DETAIL & AUDIT DRAWER PANEL */}
      {selectedRecord && (
        <div className="fixed inset-0 z-50 overflow-hidden" aria-labelledby="slide-over-title" role="dialog" aria-modal="true">
          <div className="absolute inset-0 overflow-hidden">
            {/* Backdrop */}
            <div
              className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm transition-opacity"
              onClick={() => setSelectedRecord(null)}
            />

            <div className="pointer-events-none fixed inset-y-0 right-0 flex max-w-full pl-10">
              <div className="pointer-events-auto w-screen max-w-xl border-l border-slate-800/80 bg-slate-900/95 text-[#2E2A24] shadow-2xl backdrop-blur-xl">
                <div className="flex h-full flex-col overflow-y-scroll p-6 space-y-6">

                  {/* Drawer Header */}
                  <div className="flex items-center justify-between border-b border-slate-850 pb-4">
                    <div>
                      <span className="text-[10px] font-mono text-emerald-600 bg-emerald-500/10 px-2 py-0.5 rounded font-bold">
                        Record ID: {selectedRecord.id}
                      </span>
                      <h2 className="text-base font-bold text-slate-900 mt-1">Compliance Audit Inspector</h2>
                    </div>
                    <button
                      onClick={() => setSelectedRecord(null)}
                      className="rounded-lg p-1.5 hover:bg-slate-850/60 text-slate-500 hover:text-slate-800 transition"
                    >
                      <X className="h-5 w-5" />
                    </button>
                  </div>

                  {/* Operational details status bar */}
                  <div className="grid grid-cols-2 gap-4 bg-slate-900/10 p-4 rounded-xl border border-slate-850/80">
                    <div>
                      <p className="text-[10px] text-slate-500 uppercase tracking-wide font-bold">Review Status</p>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold mt-1 inline-block ${selectedRecord.review_status === 'APPROVED'
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                          : selectedRecord.review_status === 'FLAGGED'
                            ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse'
                            : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                        }`}>
                        {selectedRecord.review_status}
                      </span>
                    </div>

                    <div>
                      <p className="text-[10px] text-slate-500 uppercase tracking-wide font-bold">Data Source Scope</p>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold mt-1 inline-block ${selectedRecord.scope === 'SCOPE_1' ? 'bg-cyan-500/10 text-cyan-400' :
                          selectedRecord.scope === 'SCOPE_2' ? 'bg-yellow-500/10 text-yellow-400' :
                            'bg-purple-500/10 text-purple-400'
                        }`}>
                        {selectedRecord.scope}
                      </span>
                    </div>
                  </div>

                  {/* Warning Anomalies Box */}
                  {selectedRecord.anomaly_flag_reason && (
                    <div className="bg-amber-500/5 border border-amber-500/20 p-4 rounded-xl space-y-1">
                      <div className="flex items-center gap-1.5 text-amber-400 text-xs font-semibold">
                        <AlertTriangle className="h-4 w-4" />
                        <span>Heuristic Anomalies Flagged</span>
                      </div>
                      <p className="text-[11px] text-amber-300/80 font-mono leading-relaxed pl-5">
                        {selectedRecord.anomaly_flag_reason}
                      </p>
                    </div>
                  )}

                  {/* Approvals audit card */}
                  {selectedRecord.review_status === 'APPROVED' && (
                    <div className="bg-emerald-500/5 border border-emerald-500/20 p-4 rounded-xl flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-emerald-400 mt-0.5" />
                      <div className="space-y-0.5">
                        <p className="text-xs font-semibold text-white">Record Audited & Signed Off</p>
                        <p className="text-[10px] text-slate-400">Auditor: {selectedRecord.approved_by_email}</p>
                        <p className="text-[10px] text-slate-500">Timestamp: {new Date(selectedRecord.approved_at).toLocaleString()}</p>
                      </div>
                    </div>
                  )}

                  {/* EDIT RECORD & VALUES OR READ-ONLY DETAIL */}
                  {!isEditing ? (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <h3 className="text-xs uppercase tracking-wider text-slate-400 font-bold">Activity Metrics</h3>
                        {selectedRecord.review_status !== 'APPROVED' && (
                          <button
                            onClick={() => setIsEditing(true)}
                            className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
                          >
                            <Edit2 className="h-3 w-3" />
                            Edit Parameters
                          </button>
                        )}
                      </div>

                      <div className="grid grid-cols-2 gap-4 bg-slate-900/10 p-4 rounded-xl border border-slate-850/80 text-xs">
                        <div>
                          <p className="text-slate-500 font-semibold">Category</p>
                          <p className="font-bold mt-1 text-slate-800">{selectedRecord.category}</p>
                        </div>
                        <div>
                          <p className="text-slate-500 font-semibold">Plant / Facility Code</p>
                          <p className="font-bold mt-1 text-slate-800 font-mono">{selectedRecord.plant_facility_code}</p>
                        </div>
                        <div>
                          <p className="text-slate-500 font-semibold">Original Quantity</p>
                          <p className="font-bold mt-1 text-slate-800 font-mono">
                            {Number(selectedRecord.original_quantity).toFixed(2)} {selectedRecord.original_unit}
                          </p>
                        </div>
                        <div>
                          <p className="text-slate-500 font-semibold">Normalized Quantity</p>
                          <p className="font-bold mt-1 text-slate-800 font-mono">
                            {Number(selectedRecord.normalized_quantity).toFixed(2)} {selectedRecord.normalized_unit}
                          </p>
                        </div>
                        <div className="col-span-2 border-t border-slate-850 pt-2.5 mt-1">
                          <p className="text-slate-500 font-semibold">Transaction Date</p>
                          <p className="font-bold mt-1 text-slate-800 font-mono">{selectedRecord.transaction_date}</p>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <form onSubmit={handleEditSubmit} className="space-y-4">
                      <h3 className="text-xs uppercase tracking-wider text-slate-400 font-bold">Modify Parameters</h3>

                      <div className="space-y-3 bg-slate-900/10 p-4 rounded-xl border border-slate-850/80 text-xs">
                        <div>
                          <label className="text-slate-500 block mb-1 font-semibold">Category</label>
                          <input
                            type="text"
                            value={editForm.category}
                            onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
                            className="w-full glass-input rounded p-1.5 text-slate-800 focus:outline-none focus:border-emerald-500 font-semibold"
                          />
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label className="text-slate-500 block mb-1 font-semibold">Original Quantity</label>
                            <input
                              type="text"
                              value={editForm.original_quantity}
                              onChange={(e) => setEditForm({ ...editForm, original_quantity: e.target.value })}
                              className="w-full glass-input rounded p-1.5 text-slate-800 focus:outline-none focus:border-emerald-500 font-mono"
                            />
                          </div>
                          <div>
                            <label className="text-slate-500 block mb-1 font-semibold">Original Unit</label>
                            <input
                              type="text"
                              value={editForm.original_unit}
                              onChange={(e) => setEditForm({ ...editForm, original_unit: e.target.value })}
                              className="w-full glass-input rounded p-1.5 text-slate-800 focus:outline-none focus:border-emerald-500"
                            />
                          </div>
                        </div>

                        <div>
                          <label className="text-slate-500 block mb-1 font-semibold">Plant / Facility Code</label>
                          <input
                            type="text"
                            value={editForm.plant_facility_code}
                            onChange={(e) => setEditForm({ ...editForm, plant_facility_code: e.target.value })}
                            className="w-full glass-input rounded p-1.5 text-slate-800 focus:outline-none focus:border-emerald-500 font-mono"
                          />
                        </div>

                        <div>
                          <label className="text-slate-500 block mb-1 font-semibold">Transaction Date</label>
                          <input
                            type="date"
                            value={editForm.transaction_date}
                            onChange={(e) => setEditForm({ ...editForm, transaction_date: e.target.value })}
                            className="w-full glass-input rounded p-1.5 text-slate-800 focus:outline-none focus:border-emerald-500 font-mono"
                          />
                        </div>
                      </div>

                      <div className="flex gap-2">
                        <button
                          type="submit"
                          className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-1.5 px-3 rounded text-xs transition"
                        >
                          Save Changes
                        </button>
                        <button
                          type="button"
                          onClick={() => setIsEditing(false)}
                          className="bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold py-1.5 px-3 rounded text-xs transition border border-slate-700"
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  )}

                  {/* RAW IMPORTED DATA PAYLOAD */}
                  <div className="space-y-2.5">
                    <h3 className="text-xs uppercase tracking-wider text-slate-500 font-bold">Raw Ingested Data Payload</h3>
                    {selectedRecord.raw_row?.payload ? (
                      <pre className="glass-input p-4 rounded-xl border border-slate-850/80 text-[10px] font-mono text-emerald-600 overflow-x-auto max-h-[160px] shadow-inner font-semibold">
                        {JSON.stringify(selectedRecord.raw_row.payload, null, 2)}
                      </pre>
                    ) : (
                      <p className="text-xs text-slate-500 italic glass-input p-4 rounded-xl border border-slate-850/80">
                        No raw data payload available for manually created records.
                      </p>
                    )}
                  </div>

                  {/* AUDITOR WORKFLOW BUTTONS */}
                  {selectedRecord.review_status !== 'APPROVED' && (
                    <div className="border-t border-slate-850 pt-4 flex gap-3">
                      <button
                        onClick={() => handleReviewAction(selectedRecord.id, 'APPROVED')}
                        className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2.5 px-4 rounded-lg text-xs transition flex items-center justify-center gap-1"
                      >
                        <Check className="h-4 w-4" />
                        Approve and Sign-off
                      </button>

                      <button
                        onClick={() => {
                          const reason = prompt("Enter anomaly description to flag this record:", selectedRecord.anomaly_flag_reason || "");
                          if (reason !== null) {
                            handleReviewAction(selectedRecord.id, 'FLAGGED', reason);
                          }
                        }}
                        className="bg-amber-600 hover:bg-amber-500 text-white font-bold py-2.5 px-4 rounded-lg text-xs transition flex items-center justify-center gap-1"
                      >
                        <Flag className="h-4 w-4" />
                        Flag Anomaly
                      </button>
                    </div>
                  )}

                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
