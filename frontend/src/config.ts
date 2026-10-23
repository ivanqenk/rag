// Debe coincidir con MAX_UPLOAD_SIZE_MB del backend. La validación en el cliente es solo una
// comodidad (avisa antes de subir); la que cuenta es la del servidor.
export const MAX_UPLOAD_MB = Number(import.meta.env.VITE_MAX_UPLOAD_MB ?? 20)
