export function portalIdFromContext(context) {
  return String(context?.portal?.id || context?.portalId || "");
}


export function recordIdFromContext(context) {
  return String(context?.crm?.objectId || context?.objectId || context?.recordId || "");
}


export function objectTypeFromContext(context) {
  return String(context?.crm?.objectType || context?.objectType || context?.objectTypeId || "");
}
