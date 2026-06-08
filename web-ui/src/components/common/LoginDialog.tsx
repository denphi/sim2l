// Username/password login dialog.
//
// Review item #W6 (initial implementation) + #T1 (login now fans out to
// every backend so all three services accept the returned session tokens) +
// #T21 (network errors render distinctly from credential errors).

import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  TextField,
} from '@mui/material';
import axios, { AxiosError } from 'axios';
import { config } from '../../config';
import {
  Service,
  onSessionInvalid,
  setSessionIds,
} from '../../api/session';

type Props = {
  open: boolean;
  onClose: () => void;
};

type LoginAttempt = {
  service: Service;
  outcome:
    | { kind: 'ok'; token: string }
    | { kind: 'credential'; message: string }
    | { kind: 'network'; message: string }
    | { kind: 'server'; message: string };
};

async function loginToService(
  service: Service,
  username: string,
  password: string
): Promise<LoginAttempt> {
  const baseUrl = config.services[service].baseUrl;
  try {
    const resp = await axios.post<{ token?: string; session_id?: string; error?: string }>(
      `${baseUrl}/session/login`,
      { username, password },
      { timeout: 10000 }
    );
    const id = resp.data?.token || resp.data?.session_id;
    if (id) {
      return { service, outcome: { kind: 'ok', token: id } };
    }
    return {
      service,
      outcome: {
        kind: 'server',
        message: resp.data?.error || 'No token in response',
      },
    };
  } catch (err) {
    const axErr = err as AxiosError<{ error?: string }>;
    if (axErr.response) {
      const detail = axErr.response.data?.error || 'Login refused';
      const kind =
        axErr.response.status === 401 || axErr.response.status === 400
          ? 'credential'
          : 'server';
      return { service, outcome: { kind, message: detail } };
    }
    // No response → axios threw before reaching the server.
    return {
      service,
      outcome: {
        kind: 'network',
        message: axErr.code === 'ECONNABORTED'
          ? 'Login timed out (service unreachable)'
          : 'Service unreachable',
      },
    };
  }
}

export function LoginDialog({ open, onClose }: Props) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!username || !password) {
      setError('Username and password are required.');
      return;
    }
    setSubmitting(true);
    setError(null);

    const services: Service[] = ['catalog', 'cache', 'results'];
    const attempts = await Promise.all(
      services.map(s => loginToService(s, username, password))
    );

    const sessions: Partial<Record<Service, string>> = {};
    const credentialErrors: string[] = [];
    const networkErrors: string[] = [];
    for (const attempt of attempts) {
      switch (attempt.outcome.kind) {
        case 'ok':
          sessions[attempt.service] = attempt.outcome.token;
          break;
        case 'credential':
          credentialErrors.push(`${attempt.service}: ${attempt.outcome.message}`);
          break;
        case 'network':
        case 'server':
          networkErrors.push(`${attempt.service}: ${attempt.outcome.message}`);
          break;
      }
    }

    setSubmitting(false);

    // If at least one credential rejection: treat as a bad-password.
    if (credentialErrors.length > 0) {
      setError('Invalid username or password.');
      return;
    }

    if (Object.keys(sessions).length === 0) {
      // Nothing came back — all attempts failed at the network level.
      setError(
        `Could not reach any sim2l service. ${networkErrors.join('; ')}`
      );
      return;
    }

    setSessionIds(sessions);
    setPassword('');

    if (networkErrors.length > 0) {
      // Partial success — user is logged in to *some* services. Show the
      // remaining errors as a warning but close the dialog so they can
      // proceed.
      console.warn(
        `[Login] Logged in to ${Object.keys(sessions).join(', ')}; some services unavailable: ${networkErrors.join('; ')}`
      );
    }
    onClose();
  };

  return (
    <Dialog open={open} onClose={submitting ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Sign in to sim2l</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>
          Provide your sim2l credentials. Each backend service issues its
          own session token; this dialog logs you into all three at once and
          stores the tokens for this browser session only. The password is
          not stored. For local authenticated services,
          use the built-in <strong>admin</strong> account and the password
          from <strong>~/.sim2l/admin_password</strong>, unless you started
          services with a custom <strong>SIM2L_ADMIN_PASSWORD</strong>.
        </DialogContentText>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        <TextField
          autoFocus
          margin="dense"
          label="Username"
          fullWidth
          value={username}
          onChange={e => setUsername(e.target.value)}
          disabled={submitting}
        />
        <TextField
          margin="dense"
          label="Password"
          type="password"
          fullWidth
          value={password}
          onChange={e => setPassword(e.target.value)}
          disabled={submitting}
          onKeyDown={e => {
            if (e.key === 'Enter') handleSubmit();
          }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>Cancel</Button>
        <Button onClick={handleSubmit} disabled={submitting} variant="contained">
          {submitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

/**
 * App-level controller: opens the dialog automatically when the API client
 * reports a 401 after refresh-retry. Wire this into the root component once.
 */
export function useAutoLogin(): { open: boolean; show: () => void; hide: () => void } {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const unsubscribe = onSessionInvalid(() => setOpen(true));
    return () => {
      // onSessionInvalid returns a teardown that removes the listener
      unsubscribe();
    };
  }, []);

  return {
    open,
    show: () => setOpen(true),
    hide: () => setOpen(false),
  };
}
