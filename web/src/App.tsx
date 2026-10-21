import { useEffect, useState } from 'react';
import { api } from './api';

export default function App() {
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<string>('/hello')
      .then(setMessage)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p>Loading...</p>;
  if (error) return <p>{error}</p>;
  return <p>Hello, {message}</p>;
}
