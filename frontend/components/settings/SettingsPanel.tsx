import { useEffect } from 'react';
import { useSettingsStore } from '@/stores/settingsStore';

export function SettingsPanel() {
  const { settings, loading, error, fetchSettings, updateSettings } = useSettingsStore();

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  if (loading) {
    return (
      <div className="p-4">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-gray-200 rounded w-1/4"></div>
          <div className="h-32 bg-gray-200 rounded"></div>
          <div className="h-4 bg-gray-200 rounded w-1/2"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="text-sm text-red-700">{error}</div>
        </div>
      </div>
    );
  }

  if (!settings) return null;

  return (
    <div className="p-4 space-y-6">
      <div>
        <h3 className="text-lg font-medium text-gray-900">Personal Information</h3>
        <div className="mt-2">
          <textarea
            rows={4}
            value={settings.personal_info}
            onChange={(e) => updateSettings({ personal_info: e.target.value })}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
            placeholder="Add information about yourself..."
          />
        </div>
      </div>

      <div>
        <h3 className="text-lg font-medium text-gray-900">OpenAI API Key</h3>
        <div className="mt-2">
          <input
            type="text"
            disabled
            className="block w-full rounded-md border-gray-300 shadow-sm bg-gray-100 text-gray-500 sm:text-sm cursor-not-allowed"
            placeholder="Coming Soon!"
          />
          <p className="mt-1 text-xs text-gray-500">This feature is coming soon!</p>
        </div>
      </div>

      <div>
        <h3 className="text-lg font-medium text-gray-900">Model</h3>
        <div className="mt-2">
          <select
            disabled
            className="block w-full rounded-md border-gray-300 shadow-sm bg-gray-100 text-gray-500 sm:text-sm cursor-not-allowed"
            defaultValue=""
          >
            <option value="" disabled>Coming Soon!</option>
          </select>
          <p className="mt-1 text-xs text-gray-500">This feature is coming soon!</p>
        </div>
      </div>
    </div>
  );
} 