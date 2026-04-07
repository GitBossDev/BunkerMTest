'use client'

import { useRef, useState } from 'react'
import { Download, Upload, FileText, CheckCircle, XCircle, Loader2, Info, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { configApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DefaultACLCard } from '@/components/mqtt/DefaultACLCard'

export default function DynSecJsonPage() {
  const [file, setFile] = useState<File | null>(null)
  const [importStatus, setImportStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle')
  const [importMessage, setImportMessage] = useState('')
  const [isExporting, setIsExporting] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] || null
    setFile(f)
    setImportStatus('idle')
    setImportMessage('')
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const f = e.dataTransfer.files[0]
    if (f) {
      setFile(f)
      setImportStatus('idle')
      setImportMessage('')
    }
  }

  const handleImport = async () => {
    if (!file) return
    setImportStatus('uploading')
    try {
      const text = await file.text()
      JSON.parse(text) // validate JSON before sending
      const formData = new FormData()
      formData.append('file', file)
      const res = await configApi.importDynSecJson(formData)
      const result = await res.json()
      if (!result.success) {
        const msg = result.message || 'Import failed'
        setImportStatus('error')
        setImportMessage(msg)
        toast.error(msg)
        return
      }
      setImportStatus('success')
      const stats = result.stats
      const statsMsg = stats ? ` (${stats.users ?? stats.clients ?? 0} users, ${stats.roles ?? 0} roles)` : ''
      setImportMessage(`Configuration imported${statsMsg} — broker reloading`)
      toast.success(`DynSec configuration imported${statsMsg}`)
    } catch (err) {
      const msg = err instanceof SyntaxError ? 'File is not valid JSON' : (err instanceof Error ? err.message : 'Failed to import configuration')
      setImportStatus('error')
      setImportMessage(msg)
      toast.error(msg)
    }
  }

  const handleExport = async () => {
    setIsExporting(true)
    try {
      const res = await configApi.exportDynSecJson()
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `dynsec-config-${Date.now()}.json`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Configuration exported')
    } catch {
      toast.error('Failed to export configuration')
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold">Security &amp; ACL</h1>
        <p className="text-muted-foreground text-sm">
          Manage default access rules and the dynamic security plugin configuration
        </p>
      </div>

      {/* Info banner */}
      <div className="flex items-start gap-3 rounded-lg border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
        <ShieldCheck className="h-4 w-4 mt-0.5 shrink-0 text-primary" />
        <span>
          The <strong className="text-foreground">Dynamic Security plugin</strong> stores all clients, groups, roles, and ACLs in a single JSON file (<code className="text-xs bg-muted px-1 rounded">dynamic-security.json</code>). Use the export button to download a backup and the import button to restore or replace the configuration. Changes require a <strong className="text-foreground">broker restart</strong> to take effect — importing a configuration will restart the broker automatically.
        </span>
      </div>

      {/* Default ACL */}
      <DefaultACLCard />

      {/* Export card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Download className="h-4 w-4" />
            Export Configuration
          </CardTitle>
          <CardDescription>
            Download the current DynSec JSON as a backup or for editing offline
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={handleExport} disabled={isExporting}>
            {isExporting
              ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              : <Download className="h-4 w-4 mr-2" />}
            Download dynsec-config.json
          </Button>
        </CardContent>
      </Card>

      {/* Import card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Upload className="h-4 w-4" />
            Import Configuration
          </CardTitle>
          <CardDescription>
            Replace the entire DynSec configuration with a JSON file. All existing clients, roles, and ACLs will be overwritten.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-start gap-2 rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
            <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span>This replaces the complete security configuration. Export a backup first if you want to preserve the current state.</span>
          </div>

          <div
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => inputRef.current?.click()}
            className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:bg-muted/50 transition-colors"
          >
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              onChange={handleFileChange}
              accept=".json,application/json"
            />
            {file ? (
              <div className="flex flex-col items-center gap-2">
                <FileText className="h-10 w-10 text-primary" />
                <p className="font-medium">{file.name}</p>
                <p className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 text-muted-foreground">
                <Upload className="h-10 w-10" />
                <p className="font-medium">Drop JSON file here or click to browse</p>
                <p className="text-xs">Accepts dynamic-security.json files</p>
              </div>
            )}
          </div>

          {importStatus !== 'idle' && (
            <div className={`flex items-center gap-2 p-3 rounded-lg text-sm ${
              importStatus === 'success' ? 'bg-green-500/10 text-green-700 dark:text-green-400' :
              importStatus === 'error' ? 'bg-destructive/10 text-destructive' :
              'bg-muted text-muted-foreground'
            }`}>
              {importStatus === 'success' && <CheckCircle className="h-4 w-4 shrink-0" />}
              {importStatus === 'error' && <XCircle className="h-4 w-4 shrink-0" />}
              {importStatus === 'uploading' && <Loader2 className="h-4 w-4 animate-spin shrink-0" />}
              <span>{importStatus === 'uploading' ? 'Importing...' : importMessage}</span>
            </div>
          )}

          <Button
            onClick={handleImport}
            disabled={!file || importStatus === 'uploading'}
          >
            {importStatus === 'uploading'
              ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              : <Upload className="h-4 w-4 mr-2" />}
            Import Configuration
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
