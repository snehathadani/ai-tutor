interface Props {
  summary: {
    summary: string;
    strengths: string[];
    next_steps: string[];
  };
  onClose: () => void;
}

export default function SummaryView({ summary, onClose }: Props) {
  return (
    <div className="card">
      <div className="form-row" style={{ justifyContent: 'space-between' }}>
        <h2>Session Summary</h2>
        <button type="button" className="secondary" onClick={onClose}>
          Close
        </button>
      </div>
      <p style={{ marginTop: '0.75rem' }}>{summary.summary}</p>
      <h3 style={{ marginTop: '0.75rem', fontSize: '1rem' }}>Strengths</h3>
      <ul>
        {summary.strengths.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ul>
      <h3 style={{ marginTop: '0.75rem', fontSize: '1rem' }}>Next steps</h3>
      <ul>
        {summary.next_steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ul>
    </div>
  );
}
