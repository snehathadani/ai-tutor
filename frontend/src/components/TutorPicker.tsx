interface Reference {
  title: string;
  url: string;
}

interface Concept {
  slug: string;
  label: string;
  references?: Reference[];
}

export interface Tutor {
  id: string;
  title: string;
  subject: string;
  description: string;
  age_range?: string;
  concept_count: number;
  concepts: Concept[];
  level_labels?: Record<number, string>;
}

interface Props {
  tutors: Tutor[];
  invalid: { id?: string; error: string }[];
  selected: Tutor | null;
  onSelect: (tutor: Tutor) => void;
}

export default function TutorPicker({ tutors, invalid, selected, onSelect }: Props) {
  return (
    <div className="card">
      <h2>Choose a tutor</h2>
      {invalid.length > 0 && (
        <div className="warning" style={{ marginTop: '0.5rem' }}>
          Warning: {invalid.length} tutor(s) failed to load. Check the server logs.
        </div>
      )}
      <div className="tutor-grid" style={{ marginTop: '0.75rem' }}>
        {tutors.map((tutor) => (
          <button
            key={tutor.id}
            type="button"
            className={`tutor-card ${selected?.id === tutor.id ? 'selected' : ''}`}
            onClick={() => onSelect(tutor)}
            aria-pressed={selected?.id === tutor.id}
          >
            <h3>{tutor.title}</h3>
            <div className="form-row">
              <span className="status">{tutor.subject}</span>
              {tutor.age_range && <span className="badge">Ages {tutor.age_range}</span>}
            </div>
            <p style={{ marginTop: '0.5rem', fontSize: '0.9rem' }}>{tutor.description}</p>
            <span className="status">{tutor.concept_count} concepts</span>
          </button>
        ))}
      </div>
    </div>
  );
}
