/**
 * Réduit une photo avant l'envoi : un cliché de téléphone de 8 Mo part en quelques centaines de Ko,
 * ce qui compte en 4G. Le serveur ré-encode de toute façon et retire les métadonnées (RG-14).
 */
const MAX_EDGE = 2000;

export async function shrinkPhoto(file: File): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && file.size < 1_500_000) return file;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.86));
    return blob ?? file;
  } catch {
    return file; // format que le navigateur ne décode pas (HEIC) : le serveur s'en charge
  }
}
