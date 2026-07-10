import client from "./client";

export const listTarget = () => client.get("/target-categories").then((r) => r.data);
export const listOffer = () => client.get("/offer-categories").then((r) => r.data);

export const createTarget = (p) => client.post("/admin/target-categories", p).then((r) => r.data);
export const updateTarget = (id, p) => client.patch(`/admin/target-categories/${id}`, p).then((r) => r.data);
export const removeTarget = (id) => client.delete(`/admin/target-categories/${id}`).then((r) => r.data);

export const createOffer = (p) => client.post("/admin/offer-categories", p).then((r) => r.data);
export const updateOffer = (id, p) => client.patch(`/admin/offer-categories/${id}`, p).then((r) => r.data);
export const removeOffer = (id) => client.delete(`/admin/offer-categories/${id}`).then((r) => r.data);
