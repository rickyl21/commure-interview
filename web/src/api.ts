// Small fetch wrapper: JSON in/out, throws a readable Error on non-2xx.
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? `${res.status} ${res.statusText}`);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

// Sends an MP4 as the raw request body and resolves with the grayscale MP4.
// Uses XHR instead of fetch because fetch can't report upload progress.
export function uploadForGrayscale(
  file: File,
  onUploadProgress: (fraction: number) => void,
  onUploadDone: () => void,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/grayscale');
    xhr.setRequestHeader('Content-Type', 'video/mp4');
    xhr.responseType = 'blob';

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onUploadProgress(e.loaded / e.total);
    };
    xhr.upload.onload = onUploadDone;

    xhr.onload = async () => {
      if (xhr.status >= 200 && xhr.status < 300) return resolve(xhr.response as Blob);
      const body = await (xhr.response as Blob)
        .text()
        .then((t) => JSON.parse(t))
        .catch(() => ({}));
      reject(new Error(body.error ?? body.detail ?? `${xhr.status} ${xhr.statusText}`));
    };
    xhr.onerror = () => reject(new Error('Network error: could not reach the server'));

    xhr.send(file);
  });
}
