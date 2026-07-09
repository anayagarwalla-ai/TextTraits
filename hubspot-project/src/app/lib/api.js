import {hubspot} from "@hubspot/ui-extensions";


const buildApiBase = typeof process !== "undefined" ? process?.env?.TEXTTRAITS_API_BASE : "";
export const API_BASE = String(
  globalThis?.TEXTTRAITS_API_BASE || buildApiBase || "https://texttraits.onrender.com",
).replace(/\/$/, "");


export async function hubspotApi(path, options = {}) {
  const {
    allowStatuses = [],
    errorMessage = "TextTraits request failed.",
    ...fetchOptions
  } = options;
  const response = await hubspot.fetch(`${API_BASE}${path}`, fetchOptions);
  let payload = {};
  try {
    payload = await response.json();
  } catch (_error) {
    payload = {};
  }
  if (!response.ok && !allowStatuses.includes(response.status)) {
    const error = new Error(payload.error || errorMessage);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return {payload, response, status: response.status};
}
