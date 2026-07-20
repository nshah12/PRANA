export const mockCareer = {
  employers: [
    { id: 'e1', name: 'NPCI', role: 'Senior Engineer', from: '2022-04-01', to: null },
    { id: 'e2', name: 'Infosys', role: 'Software Engineer', from: '2019-03-01', to: '2022-03-31' },
  ],
  events: [
    { id: 'ev1', type: 'promotion', label: 'Promoted to Senior Engineer', employer_id: 'e1', at: '2024-01-15' },
    { id: 'ev2', type: 'join', label: 'Joined NPCI', employer_id: 'e1', at: '2022-04-01' },
    { id: 'ev3', type: 'leave', label: 'Left Infosys', employer_id: 'e2', at: '2022-03-31' },
    { id: 'ev4', type: 'join', label: 'Joined Infosys', employer_id: 'e2', at: '2019-03-01' },
  ],
};
