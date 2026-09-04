import client from "./client";

// Останній health-снапшот краулера (null, поки він жодного разу не зголосився).
export const get = () => client.get("/admin/crawler-health").then((r) => r.data);
