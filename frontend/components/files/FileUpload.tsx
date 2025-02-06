import { useRef, useState, useEffect } from 'react';
import { useFileStore } from '@/stores/fileStore';
import { DocumentPlusIcon } from '@heroicons/react/24/outline';

export function FileUpload() {
  const { totalFiles, uploadFile, uploading, fetchTotalFiles } = useFileStore();
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchTotalFiles();
  }, [fetchTotalFiles]);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      await handleFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files) {
      await handleFiles(Array.from(e.target.files));
    }
  };

  const handleFiles = async (files: File[]) => {
    for (const file of files) {
      try {
        await uploadFile(file);
        // Refresh the total count after upload
        fetchTotalFiles();
      } catch (error) {
        console.error(`Error uploading ${file.name}:`, error);
      }
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b">
        <h2 className="text-lg font-medium text-gray-900">
          Documents ({totalFiles ?? 0} indexed)
        </h2>
      </div>

      <div className="flex-1 p-4">
        <div
          className={`relative border-2 border-dashed rounded-lg p-6 ${
            dragActive
              ? 'border-indigo-500 bg-indigo-50'
              : 'border-gray-300 hover:border-gray-400'
          }`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        >
          <input
            ref={inputRef}
            type="file"
            multiple
            onChange={handleChange}
            accept=".txt,.pdf,.md,.doc,.docx"
            className="hidden"
          />

          <div className="text-center">
            <DocumentPlusIcon className="mx-auto h-12 w-12 text-gray-400" />
            <div className="mt-4">
              <button
                type="button"
                disabled={uploading}
                onClick={() => inputRef.current?.click()}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {uploading ? 'Uploading...' : 'Select files'}
              </button>
            </div>
            <p className="mt-2 text-sm text-gray-500">
              or drag and drop files here
            </p>
          </div>
        </div>
      </div>
    </div>
  );
} 