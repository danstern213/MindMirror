import { useFileStore } from '@/stores/fileStore';

export function UploadProgress() {
  const { uploadProgress } = useFileStore();
  const { currentFile, currentFileIndex, totalFiles, status } = uploadProgress;

  if (status === 'idle') return null;

  const progress = Math.round(((currentFileIndex + 1) / totalFiles) * 100);
  
  const getStatusColor = () => {
    switch (status) {
      case 'uploading':
        return 'bg-blue-600';
      case 'processing':
        return 'bg-indigo-600';
      case 'complete':
        return 'bg-green-600';
      case 'error':
        return 'bg-red-600';
      default:
        return 'bg-gray-600';
    }
  };

  const getStatusText = () => {
    switch (status) {
      case 'uploading':
        return `Uploading ${currentFile}...`;
      case 'processing':
        return `Processing ${currentFile}...`;
      case 'complete':
        return 'Upload complete';
      case 'error':
        return 'Upload failed';
      default:
        return '';
    }
  };

  return (
    <div className="w-full">
      <div className="flex justify-between mb-1">
        <span className="text-sm font-medium text-gray-700">
          {getStatusText()}
        </span>
        <span className="text-sm font-medium text-gray-700">
          {currentFileIndex + 1} of {totalFiles} ({progress}%)
        </span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2.5">
        <div
          className={`h-2.5 rounded-full transition-all duration-300 ${getStatusColor()}`}
          style={{ width: `${progress}%` }}
        ></div>
      </div>
    </div>
  );
} 