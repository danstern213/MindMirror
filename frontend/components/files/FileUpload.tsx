import { useRef, useState, useEffect } from 'react';
import { useFileStore } from '@/stores/fileStore';
import { DocumentPlusIcon } from '@heroicons/react/24/outline';
import { XCircleIcon } from '@heroicons/react/20/solid';

export function FileUpload() {
  const { totalFiles, uploadFile, uploading, error, fetchTotalFiles, clearError } = useFileStore();
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
    clearError();

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      await handleFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    clearError();
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
        // Error is handled by the store and displayed below
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
        {error && (
          <div className="rounded-md bg-red-50 p-4 mb-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <XCircleIcon className="h-5 w-5 text-red-400" aria-hidden="true" />
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-red-800">Upload Error</h3>
                <div className="mt-2 text-sm text-red-700">
                  <p>{error}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        <div
          className={`relative border-2 border-dashed rounded-lg p-6 ${
            dragActive
              ? 'border-indigo-500 bg-indigo-50'
              : error
              ? 'border-red-300 hover:border-red-400'
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
                onClick={() => {
                  clearError();
                  inputRef.current?.click();
                }}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {uploading ? 'Uploading...' : 'Select files'}
              </button>
            </div>
            <p className="mt-2 text-sm text-gray-500">
              or drag and drop files here
            </p>
            <p className="mt-1 text-xs text-gray-500">
              Supported formats: .txt, .pdf, .md, .doc, .docx (max 10MB)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
} 