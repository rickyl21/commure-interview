import { useState, type ChangeEvent } from 'react';
import { uploadForGrayscale } from './api';

const MAX_FILES = 2;

type Status = 'uploading' | 'processing' | 'done' | 'error';

type Job = {
  id: number;
  name: string;
  status: Status;
  progress: number;
  error: string;
  originalUrl: string | null;
  grayscaleUrl: string | null;
};

let nextId = 0;

export default function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState('');

  const busy = jobs.some((j) => j.status === 'uploading' || j.status === 'processing');

  function update(id: number, patch: Partial<Job>) {
    setJobs((js) => js.map((j) => (j.id === id ? { ...j, ...patch } : j)));
  }

  async function runJob(id: number, file: File) {
    try {
      const blob = await uploadForGrayscale(
        file,
        (progress) => update(id, { progress }),
        () => update(id, { status: 'processing' }),
      );
      update(id, {
        status: 'done',
        originalUrl: URL.createObjectURL(file),
        grayscaleUrl: URL.createObjectURL(blob),
      });
    } catch (err) {
      update(id, { status: 'error', error: (err as Error).message });
    }
  }

  function handleFiles(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = ''; // allow re-selecting the same files
    if (files.length === 0) return;
    if (files.length > MAX_FILES) {
      setError(`Choose at most ${MAX_FILES} videos.`);
      return;
    }
    setError('');

    // Free the previous results' blob URLs before replacing them.
    for (const j of jobs) {
      if (j.originalUrl) URL.revokeObjectURL(j.originalUrl);
      if (j.grayscaleUrl) URL.revokeObjectURL(j.grayscaleUrl);
    }

    const newJobs = files.map((file): Job => {
      const valid = file.type === 'video/mp4';
      return {
        id: nextId++,
        name: file.name,
        status: valid ? 'uploading' : 'error',
        progress: 0,
        error: valid ? '' : 'Not an MP4 file.',
        originalUrl: null,
        grayscaleUrl: null,
      };
    });
    setJobs(newJobs);
    newJobs.forEach((job, i) => {
      if (job.status === 'uploading') runJob(job.id, files[i]);
    });
  }

  return (
    <main>
      <h1>Grayscale video converter</h1>
      <label>
        Upload up to {MAX_FILES} MP4s:{' '}
        <input type="file" accept="video/mp4" multiple onChange={handleFiles} disabled={busy} />
      </label>
      {error && <p role="alert">Error: {error}</p>}

      {jobs.map((job) => (
        <section key={job.id} style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: '1.1em' }}>{job.name}</h2>
          {job.status === 'uploading' && <p>Uploading... {Math.round(job.progress * 100)}%</p>}
          {job.status === 'processing' && <p>Processing...</p>}
          {job.status === 'error' && <p role="alert">Error: {job.error}</p>}

          {job.status === 'done' && job.originalUrl && job.grayscaleUrl && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
              <figure style={{ flex: '1 1 320px', margin: 0 }}>
                <figcaption>Original</figcaption>
                <video src={job.originalUrl} controls style={{ width: '100%' }} />
              </figure>
              <figure style={{ flex: '1 1 320px', margin: 0 }}>
                <figcaption>Grayscale</figcaption>
                <video src={job.grayscaleUrl} controls style={{ width: '100%' }} />
              </figure>
            </div>
          )}
        </section>
      ))}
    </main>
  );
}
