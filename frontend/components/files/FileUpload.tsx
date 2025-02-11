import { useRef, useState, useEffect } from 'react';
import { useFileStore } from '@/stores/fileStore';
import { DocumentPlusIcon } from '@heroicons/react/24/outline';
import { XCircleIcon } from '@heroicons/react/20/solid';
import toast from 'react-hot-toast';
import { UploadProgress } from './UploadProgress';

export function FileUpload() {
  const { totalFiles, uploadFile, uploading, error, fetchTotalFiles, clearError, setUploadProgress } = useFileStore();
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
      const files = Array.from(e.dataTransfer.files);
      setUploadProgress({
        currentFileIndex: 0,
        totalFiles: files.length,
        status: 'idle'
      });
      await handleFiles(files);
      // Reset the input after drag and drop
      if (inputRef.current) {
        inputRef.current.value = '';
      }
    }
  };

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    clearError();
    if (e.target.files) {
      const files = Array.from(e.target.files);
      setUploadProgress({
        currentFileIndex: 0,
        totalFiles: files.length,
        status: 'idle'
      });
      await handleFiles(files);
      // Reset the input value so the same file can be selected again
      e.target.value = '';
    }
  };

  const handleFiles = async (files: File[]) => {
    let successCount = 0;
    let skipCount = 0;
    let errorCount = 0;

    // Always show individual toasts, but let the Toaster component handle limiting to 3
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      try {
        setUploadProgress({
          currentFileIndex: i,
          currentFile: file.name,
          status: 'uploading'
        });

        const response = await uploadFile(file);
        
        // Handle different file upload responses
        if (response.status === 'skipped' && response.embedding_status === 'skipped_duplicate') {
          toast(`${file.name} already exists and was skipped`, {
            icon: '⚠️',
          });
          skipCount++;
        } else if (file.size === 0) {
          toast(`${file.name} was saved without content`, {
            icon: 'ℹ️',
          });
          successCount++;
        } else if (response.status === 'success') {
          if (response.embedding_status === 'error') {
            toast(`${file.name} uploaded but indexing failed. You can try uploading again.`, {
              icon: '⚠️',
              duration: 5000, // Show for longer since it's important
            });
            successCount++; // Still count as success since file was saved
          } else {
            toast.success(`${file.name} uploaded and indexed successfully`);
            successCount++;
          }
        } else {
          toast.error(`Failed to process ${file.name}`);
          errorCount++;
        }
        
        // Refresh the total count after upload
        fetchTotalFiles();
      } catch (error) {
        console.error(`Error uploading ${file.name}:`, error);
        toast.error(`Failed to upload ${file.name}`);
        errorCount++;
      }
    }

    // Show final batch summary for multiple files
    if (files.length > 1) {
      const summary = [];
      if (successCount > 0) summary.push(`${successCount} uploaded`);
      if (skipCount > 0) summary.push(`${skipCount} skipped`);
      if (errorCount > 0) summary.push(`${errorCount} failed`);
      
      toast(`Batch upload complete: ${summary.join(', ')}`, {
        icon: '📊',
        duration: 5000, // Show summary for longer
      });
    }

    // Reset progress
    setUploadProgress({
      currentFileIndex: 0,
      totalFiles: 0,
      currentFile: '',
      status: 'idle'
    });
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b">
        <h2 className="text-lg font-medium text-gray-900">
          Documents ({totalFiles ?? 0} indexed)
        </h2>
      </div>

      <div className="flex-1 p-4">
        {error && !error.includes('already exists') && (
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
              <br />
              Empty files will be saved without content
            </p>
          </div>

          <div className="mt-4">
            <UploadProgress />
          </div>
        </div>
      </div>
    </div>
  );
} 