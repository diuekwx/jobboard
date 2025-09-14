

interface KanbanCardProps {
  id: string;
  company?: string;
  date: string;
}

const KanbanCard  = ({ id, company, date }: KanbanCardProps) => {
  return (
    <>
    <div className="bg-gray-700 rounded-xl p-4 shadow-md hover:shadow-lg transition-shadow duration-200">
      <h3 className="text-lg font-semibold">{company}</h3>
      <p className="text-sm text-gray-400 mt-2">Applied: {date}</p>
      <p className="text-xs text-gray-300">{id}</p>
    </div>
    </>
  );
};


export default KanbanCard