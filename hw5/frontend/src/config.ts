// The one setting for the backend address. Override with VITE_API_BASE (e.g. "npm run dev:scratch").
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";
