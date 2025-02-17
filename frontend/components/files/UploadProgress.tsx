import { useFileStore } from '@/stores/fileStore';

export function UploadProgress() {
  const { uploadProgress } = useFileStore();
  const { currentFile, currentFileIndex, totalFiles, status } = uploadProgress;

  if (status === 'idle') return null;

  const progress = Math.round(((currentFileIndex + 1) / totalFiles) * 100);
  
  const getStatusColor = () => {
    switch (status) {
      case 'uploading':
        return 'bg-[var(--primary-accent)]';
      case 'processing':
        return 'bg-[var(--primary-dark)]';
      case 'complete':
        return 'bg-[var(--primary-gold)]';
      case 'error':
        return 'bg-[#8B0000]'; // Dark red to match theme
      default:
        return 'bg-[var(--primary-dark)]';
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
    <div className="w-full mt-4">
      <div className="flex justify-between mb-1">
        <span className="text-sm font-serif text-[var(--primary-dark)]">
          {getStatusText()}
        </span>
        <span className="text-sm font-serif text-[var(--primary-dark)]">
          {currentFileIndex + 1} of {totalFiles} ({progress}%)
        </span>
      </div>
      <div className="w-full bg-[var(--paper-texture)] border border-[var(--primary-dark)] rounded-sm h-2.5">
        <div
          className={`h-2.5 rounded-sm transition-all duration-300 ${getStatusColor()}`}
          style={{ width: `${progress}%` }}
        ></div>
      </div>
    </div>
  );
} 