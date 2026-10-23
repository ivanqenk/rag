import { MAX_UPLOAD_MB } from './config'

/** Comprobación previa en el cliente. Devuelve un mensaje de error o null si parece válido.
 *  Es solo una comodidad: el servidor vuelve a validar todo (tipo real, contenido, tamaño). */
export function validateFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith('.pdf')) return 'Solo se admiten archivos PDF.'
  if (file.size === 0) return 'El archivo está vacío.'
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `El archivo supera el máximo de ${MAX_UPLOAD_MB} MB.`
  }
  return null
}
