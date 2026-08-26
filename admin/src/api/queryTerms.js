import client from "./client";

export const list = (params) => client.get("/admin/query-terms", { params }).then((r) => r.data);
export const approve = (id) => client.post(`/admin/query-terms/${id}/approve`).then((r) => r.data);
export const reject = (id) => client.post(`/admin/query-terms/${id}/reject`).then((r) => r.data);
export const unreject = (id) => client.post(`/admin/query-terms/${id}/unreject`).then((r) => r.data);
export const toPending = (id) => client.post(`/admin/query-terms/${id}/to-pending`).then((r) => r.data);
// Задача 5C: людський override
export const manualAdd = (term) => client.post("/admin/query-terms", { term }).then((r) => r.data);
export const protect = (id) => client.post(`/admin/query-terms/${id}/protect`).then((r) => r.data);
export const unprotect = (id) => client.post(`/admin/query-terms/${id}/unprotect`).then((r) => r.data);
