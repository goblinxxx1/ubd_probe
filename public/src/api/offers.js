import client from "./client";

export const list = (params) => client.get("/offers", { params }).then((r) => r.data);
export const get = (id, preview = false) =>
  client.get(`/offers/${id}`, { params: preview ? { preview: true } : {} }).then((r) => r.data);
export const locations = () => client.get("/locations").then((r) => r.data);
export const facets = (params) => client.get("/facets", { params }).then((r) => r.data);
