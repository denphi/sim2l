// Type-to-confirm dialog for destructive operations.
//
// Review item #W4/#W5: replaces `window.confirm` for irreversible actions
// like "Clear All". The user must type a phrase (default: "DELETE ALL")
// before the destructive button enables, which prevents accidental
// double-Enter dismissals.

import { useState } from 'react';
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

type Props = {
  open: boolean;
  title: string;
  description: string;
  confirmPhrase?: string;
  confirmLabel?: string;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
};

export function ConfirmDestructiveDialog({
  open,
  title,
  description,
  confirmPhrase = 'DELETE ALL',
  confirmLabel = 'Delete',
  onConfirm,
  onClose,
}: Props) {
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const matches = typed.trim() === confirmPhrase;

  const handleConfirm = async () => {
    if (!matches) return;
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      setTyped('');
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Operation failed.');
    } finally {
      setBusy(false);
    }
  };

  const handleClose = () => {
    if (busy) return;
    setTyped('');
    setError(null);
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>{description}</DialogContentText>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        <DialogContentText sx={{ mb: 1 }}>
          Type <strong>{confirmPhrase}</strong> to confirm:
        </DialogContentText>
        <TextField
          autoFocus
          fullWidth
          value={typed}
          onChange={e => setTyped(e.target.value)}
          disabled={busy}
          placeholder={confirmPhrase}
          onKeyDown={e => {
            if (e.key === 'Enter' && matches) handleConfirm();
          }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={busy}>
          Cancel
        </Button>
        <Button
          color="error"
          variant="contained"
          disabled={!matches || busy}
          onClick={handleConfirm}
        >
          {busy ? 'Working…' : confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
