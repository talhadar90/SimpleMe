import { Layers } from 'lucide-react'

export default function TexturePreview({ textureUrl, baseUrl }) {
  if (!textureUrl) {
    return null
  }

  const fullTextureUrl = textureUrl.startsWith('http') ? textureUrl : `${baseUrl}${textureUrl}`

  return (
    <div className="texture-preview">
      <div className="preview-header">
        <h3><Layers size={18} /> UV Print Texture</h3>
        <p className="preview-description">
          High-resolution texture for UV printing (130mm x 170mm @ 300 DPI)
        </p>
      </div>

      <div className="preview-container">
        <img
          src={fullTextureUrl}
          alt="UV Texture"
          className="preview-layer texture-layer"
        />
      </div>
    </div>
  )
}
