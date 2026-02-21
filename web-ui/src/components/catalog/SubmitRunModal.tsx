import { useState, useEffect } from 'react';
import {
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    Button,
    TextField,
    Typography,
    Box,
    CircularProgress,
    Alert,
} from '@mui/material';
import { catalogService } from '../../api/catalogService';
import type { Simulation } from '../../types/catalog';
import { useNavigate } from 'react-router-dom';

interface SubmitRunModalProps {
    open: boolean;
    onClose: () => void;
    simulationName: string;
    simulationVersion?: string;
}

export function SubmitRunModal({ open, onClose, simulationName, simulationVersion }: SubmitRunModalProps) {
    const [simulation, setSimulation] = useState<Simulation | null>(null);
    const [params, setParams] = useState<Record<string, any>>({});
    const [loading, setLoading] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const navigate = useNavigate();

    useEffect(() => {
        if (open && simulationName) {
            loadSimulationDetails();
        } else {
            // Reset state on close
            setSimulation(null);
            setParams({});
            setError(null);
        }
    }, [open, simulationName, simulationVersion]);

    const loadSimulationDetails = async () => {
        setLoading(true);
        setError(null);
        try {
            const simDetails = await catalogService.getSimulation(simulationName, simulationVersion);
            setSimulation(simDetails);

            // Initialize default values from schema if available
            const defaultParams: Record<string, any> = {};
            if (simDetails.input_schema) {
                Object.entries(simDetails.input_schema).forEach(([key, schemaDef]: [string, any]) => {
                    if (schemaDef && schemaDef.default !== undefined) {
                        defaultParams[key] = schemaDef.default;
                    } else if (schemaDef.type === 'Number' || schemaDef.type === 'number') {
                        defaultParams[key] = 0;
                    } else if (schemaDef.type === 'Text' || schemaDef.type === 'string') {
                        defaultParams[key] = '';
                    }
                });
            }
            setParams(defaultParams);
        } catch (err: any) {
            console.error('Failed to load simulation schema:', err);
            setError('Could not load simulation details or parameter schema.');
        } finally {
            setLoading(false);
        }
    };

    const handleChange = (key: string, value: string, type: string) => {
        let parsedValue: any = value;
        if (type === 'Number' || type === 'number') {
            parsedValue = value === '' ? '' : Number(value);
        }
        setParams(prev => ({ ...prev, [key]: parsedValue }));
    };

    const handleSubmit = async () => {
        setSubmitting(true);
        setError(null);
        try {
            // Ensure numerical conversion
            const processedParams = { ...params };
            if (simulation?.input_schema) {
                Object.entries(simulation.input_schema).forEach(([key, schemaDef]: [string, any]) => {
                    if ((schemaDef.type === 'Number' || schemaDef.type === 'number') && typeof processedParams[key] === 'string') {
                        processedParams[key] = Number(processedParams[key]);
                    }
                });
            }

            const response = await catalogService.submitRun({
                simulation_name: simulation?.name || simulationName,
                version: simulation?.version || simulationVersion,
                params: processedParams,
            });

            if (response.success) {
                onClose();
                // Maybe navigate to results page or show success toast
                navigate('/results');
            } else {
                setError(response.error || 'Execution failed');
            }
        } catch (err: any) {
            setError(err.message || 'An error occurred submitting the run');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>
                Submit New Run: {simulationName} {simulationVersion ? `v${simulationVersion}` : ''}
            </DialogTitle>
            <DialogContent>
                {loading ? (
                    <Box display="flex" justifyContent="center" p={3}>
                        <CircularProgress />
                    </Box>
                ) : error ? (
                    <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>
                ) : simulation ? (
                    <Box sx={{ mt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
                        <Typography variant="body2" color="textSecondary" gutterBottom>
                            {simulation.description}
                        </Typography>
                        {simulation.input_schema ? (
                            Object.entries(simulation.input_schema).map(([key, schemaDef]: [string, any]) => (
                                <TextField
                                    key={key}
                                    label={schemaDef.label || key}
                                    type={(schemaDef.type === 'Number' || schemaDef.type === 'number') ? 'number' : 'text'}
                                    value={params[key] !== undefined ? params[key] : ''}
                                    onChange={(e) => handleChange(key, e.target.value, schemaDef.type)}
                                    helperText={schemaDef.description}
                                    fullWidth
                                    required
                                />
                            ))
                        ) : (
                            <Typography variant="body2" color="warning.main">
                                No input schema available to generate form fields.
                            </Typography>
                        )}
                    </Box>
                ) : null}
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose} disabled={submitting}>Cancel</Button>
                <Button
                    onClick={handleSubmit}
                    variant="contained"
                    color="primary"
                    disabled={loading || submitting || !!error || !simulation}
                >
                    {submitting ? <CircularProgress size={24} /> : 'Submit Run'}
                </Button>
            </DialogActions>
        </Dialog>
    );
}
