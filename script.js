// Configuration
const API_BASE = 'https://1c0aaff4c3ab.ngrok-free.app';
let currentJobId = null;
let statusInterval = null;
let availableStyles = [];

// DOM Elements
const uploadForm = document.getElementById('uploadForm');
const submitBtn = document.getElementById('submitBtn');
const submitText = document.getElementById('submitText');
const submitLoading = document.getElementById('submitLoading');
const resultDiv = document.getElementById('result');
const jobIdSpan = document.getElementById('jobId');
const jobStyleSpan = document.getElementById('jobStyle');
const jobTimeSpan = document.getElementById('jobTime');
const statusBtn = document.getElementById('statusBtn');
const statusText = document.getElementById('statusText');
const statusLoading = document.getElementById('statusLoading');
const statusResult = document.getElementById('statusResult');
const imagesContainer = document.getElementById('imagesContainer');
const styleSelect = document.getElementById('style');
const styleDescription = document.getElementById('styleDescription');
const generationConfig = document.getElementById('generationConfig');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingStatus = document.getElementById('loadingStatus');
const progressFill = document.getElementById('progressFill');

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    loadAvailableStyles();
    setupEventListeners();
});

// Load available styles from API
async function loadAvailableStyles() {
    try {
        styleSelect.innerHTML = '<option value="">Loading styles...</option>';
        styleSelect.disabled = true;
        
        const response = await fetch(`${API_BASE}/available-styles`);
        const data = await response.json();
        
        console.log('Styles API Response:', data);
        
        if (response.ok) {
            if (data.available_styles && typeof data.available_styles === 'object') {
                const stylesObject = data.available_styles;
                const styles = Object.keys(stylesObject).map(styleName => {
                    const styleData = stylesObject[styleName];
                    return {
                        name: styleName,
                        display_name: styleData.display_name || styleData.name || styleName.charAt(0).toUpperCase() + styleName.slice(1),
                        description: styleData.description || `${styleName} style theme`,
                        emoji: styleData.emoji || '🎨',
                        character_style: styleData.character_style || '',
                        accessory_style: styleData.accessory_style || '',
                        generation_config: styleData.generation_config || {
                            size: '1024x1536',
                            quality: 'high',
                            background: 'transparent',
                            model: 'gpt-image-1'
                        },
                        accessory_hints: styleData.accessory_hints || {}
                    };
                });
                
                console.log('Processed styles:', styles);
                
                if (styles.length > 0) {
                    availableStyles = styles;
                    populateStyleDropdown(styles);
                    
                    // Set default style if provided
                    if (data.default_style && styleSelect) {
                        styleSelect.value = data.default_style;
                        // Trigger change event to update UI
                        setTimeout(() => {
                            styleSelect.dispatchEvent(new Event('change'));
                        }, 100);
                    }
                    
                    showNotification('✨ Styles loaded successfully!', 'success');
                } else {
                    throw new Error('No styles found in response');
                }
            } else {
                throw new Error('Invalid response structure - missing available_styles');
            }
        } else {
            throw new Error(data.detail || `HTTP ${response.status}: ${response.statusText}`);
        }
    } catch (error) {
        console.error('Error loading styles:', error);
        styleSelect.innerHTML = '<option value="">Error loading styles</option>';
        
        // Add fallback options
        const fallbackStyles = [
            { value: 'fantasy', text: '🧙‍♂️ Fantasy Adventure' },
            { value: 'corporate', text: '💼 Business Professional' },
            { value: 'gen_z', text: '📱 Gen-Z Trendy' },
            { value: 'cyberpunk', text: '🤖 Cyberpunk Future' },
            { value: 'retro', text: '📼 Retro Nostalgia' }
        ];
        
        fallbackStyles.forEach(style => {
            const option = document.createElement('option');
            option.value = style.value;
            option.textContent = style.text;
            styleSelect.appendChild(option);
        });
        
        showNotification('⚠️ Could not load styles from server. Using fallback options.', 'warning');
    } finally {
        styleSelect.disabled = false;
    }
}

// Populate style dropdown
function populateStyleDropdown(styles) {
    styleSelect.innerHTML = '<option value="">Choose a style theme...</option>';
    
    styles.forEach(style => {
        const option = document.createElement('option');
        option.value = style.name;
        option.textContent = `${style.emoji || '🎨'} ${style.display_name}`;
        option.dataset.description = style.description;
        option.dataset.characterStyle = style.character_style;
        option.dataset.accessoryStyle = style.accessory_style;
        styleSelect.appendChild(option);
    });
}

// Setup event listeners
function setupEventListeners() {
    // Style selection change
    styleSelect.addEventListener('change', function() {
        const selectedStyle = this.value;
        if (selectedStyle) {
            const style = availableStyles.find(s => s.name === selectedStyle);
            if (style) {
                updateStyleDescription(style);
                updateAccessoryHints(style);
                showGenerationConfig(style);
            }
        } else {
            hideGenerationConfig();
            resetAccessoryHints();
        }
    });

    // Form submission
    uploadForm.addEventListener('submit', handleFormSubmission);
}

// Update style description
function updateStyleDescription(style) {
    const description = style.description || `${style.display_name} style theme`;
    styleDescription.innerHTML = `
        <strong>${style.display_name}:</strong> ${description}
        <button type="button" class="style-preview-btn" onclick="showStyleModal('${style.name}')">
            👁️ Preview
        </button>
    `;
}

// Update accessory hints based on style
function updateAccessoryHints(style) {
    const hints = style.accessory_hints || {};
    
    document.getElementById('accessory1Hint').textContent = 
        hints.accessory_1 || `Enter an accessory that matches the ${style.display_name} style`;
    document.getElementById('accessory2Hint').textContent = 
        hints.accessory_2 || `Enter a second accessory for your ${style.display_name} character`;
    document.getElementById('accessory3Hint').textContent = 
        hints.accessory_3 || `Enter a third accessory to complete the ${style.display_name} set`;

    // Update placeholders
    document.getElementById('accessory1').placeholder = hints.accessory_1_example || 'e.g., sword, staff, weapon';
    document.getElementById('accessory2').placeholder = hints.accessory_2_example || 'e.g., shield, cape, armor';
    document.getElementById('accessory3').placeholder = hints.accessory_3_example || 'e.g., boots, helmet, belt';
}

// Reset accessory hints
function resetAccessoryHints() {
    document.getElementById('accessory1Hint').textContent = 'Enter an accessory that matches your chosen style';
    document.getElementById('accessory2Hint').textContent = 'Enter a second accessory for your character';
    document.getElementById('accessory3Hint').textContent = 'Enter a third accessory to complete the set';
    
    document.getElementById('accessory1').placeholder = 'e.g., medieval sword, magic staff, laser gun';
    document.getElementById('accessory2').placeholder = 'e.g., knight shield, cape, armor helmet';
    document.getElementById('accessory3').placeholder = 'e.g., combat boots, backpack, utility belt';
}

// Show generation configuration
function showGenerationConfig(style) {
    const config = style.generation_config || {};
    
    document.getElementById('configSize').textContent = config.size || '1024x1536';
    document.getElementById('configQuality').textContent = config.quality || 'High';
    document.getElementById('configBackground').textContent = config.background || 'Transparent';
    document.getElementById('configModel').textContent = config.model || 'dall-e-3';
    
    generationConfig.style.display = 'block';
}

// Hide generation configuration
function hideGenerationConfig() {
    generationConfig.style.display = 'none';
}

// Show style modal
function showStyleModal(styleName) {
    const style = availableStyles.find(s => s.name === styleName);
    if (!style) return;
    
    document.getElementById('modalStyleName').textContent = `${style.emoji || '🎨'} ${style.display_name}`;
    document.getElementById('modalStyleDescription').textContent = style.description || `${style.display_name} style theme`;
    document.getElementById('modalCharacterStyle').textContent = style.character_style || 'Character styling information not available';
    document.getElementById('modalAccessoryStyle').textContent = style.accessory_style || 'Accessory styling information not available';
    
    document.getElementById('styleModal').style.display = 'block';
}

// Close style modal
function closeStyleModal() {
    document.getElementById('styleModal').style.display = 'none';
}

// Form submission handler
async function handleFormSubmission(e) {
    e.preventDefault();
    
    // Validate form
    if (!validateForm()) return;
    
    // Show loading overlay
    showLoadingOverlay();
    
    // Create form data
    const formData = new FormData();
    formData.append('user_image', document.getElementById('userImage').files[0]);
    formData.append('style', document.getElementById('style').value);
    formData.append('accessory_1', document.getElementById('accessory1').value.trim());
    formData.append('accessory_2', document.getElementById('accessory2').value.trim());
    formData.append('accessory_3', document.getElementById('accessory3').value.trim());
    
    try {
        updateLoadingStatus('Uploading image and submitting job...');
        updateProgress(10);
        
        const response = await fetch(`${API_BASE}/submit-job`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            // Success - show result section
            currentJobId = result.job_id;
            const selectedStyle = availableStyles.find(s => s.name === styleSelect.value);
            
            jobIdSpan.textContent = result.job_id;
            jobStyleSpan.textContent = selectedStyle ? selectedStyle.display_name : 'Default';
            jobTimeSpan.textContent = new Date().toLocaleString();
            
            // Hide loading overlay and show results
            hideLoadingOverlay();
            resultDiv.style.display = 'block';
            
            // Clear previous results
            statusResult.innerHTML = '';
            imagesContainer.innerHTML = '';
            
            // Scroll to result section
            resultDiv.scrollIntoView({ behavior: 'smooth' });
            
            // Auto-check status every 3 seconds
            checkStatus();
            statusInterval = setInterval(checkStatus, 3000);
            
            showNotification('🎉 Job submitted successfully!', 'success');
        } else {
            throw new Error(result.detail || 'Unknown error');
        }
    } catch (error) {
        hideLoadingOverlay();
        showNotification('❌ Error: ' + error.message, 'error');
        console.error('Submission error:', error);
    }
}

// Show loading overlay
function showLoadingOverlay() {
    loadingOverlay.style.display = 'flex';
    updateProgress(0);
    updateLoadingStatus('Initializing...');
}

// Hide loading overlay
function hideLoadingOverlay() {
    loadingOverlay.style.display = 'none';
}

// Update loading status
function updateLoadingStatus(status) {
    if (loadingStatus) {
        loadingStatus.textContent = status;
    }
}

// Update progress bar
function updateProgress(percentage) {
    if (progressFill) {
        progressFill.style.width = percentage + '%';
    }
}

// Check job status
async function checkStatus() {
    if (!currentJobId) return;
    
    console.log('🔍 Starting status check for job:', currentJobId);
    
    // Show loading state
    setStatusButtonLoading(true);
    
    try {
        console.log('🔍 Fetching status from:', `${API_BASE}/job-status/${currentJobId}`);
        const response = await fetch(`${API_BASE}/job-status/${currentJobId}`);
        const status = await response.json();
        
        console.log('🔍 Raw API response:', response.status, response.ok);
        console.log('🔍 Parsed status data:', JSON.stringify(status, null, 2));
        
        if (response.ok) {
            console.log('🔍 Calling displayStatus with:', status);
            displayStatus(status);
            
            // Display results if completed
            if (status.status === 'completed' && status.result) {
                console.log('🔍 Job completed, processing results...');
                if (status.result.generated_images) {
                    console.log('🔍 Displaying images:', status.result.generated_images.length);
                    displayImages(status.result.generated_images);
                }
                if (status.result.models_3d) {
                    console.log('🔍 Displaying 3D models:', status.result.models_3d.length);
                    displayModels(status.result.models_3d);
                }
                if (status.result.blender_result) {
                    console.log('🔍 Displaying final files:', status.result.blender_result);
                    displayFinalFiles(status.result.blender_result);
                }
                stopAutoRefresh();
                showNotification('🎉 3D Starter Pack completed successfully!', 'success');
            }
            
            // Stop auto-refresh if failed
            if (status.status === 'failed') {
                console.log('🔍 Job failed:', status.error);
                stopAutoRefresh();
                showNotification('❌ Job failed: ' + (status.error || 'Unknown error'), 'error');
            }
        } else {
            throw new Error(response.statusText || 'Failed to fetch status');
        }
    } catch (error) {
        console.error('🔍 ERROR in checkStatus:', error);
        console.error('🔍 Error stack:', error.stack);
        statusResult.innerHTML = `
            <div class="status failed">
                <h4>❌ Error Checking Status</h4>
                <p><strong>Error:</strong> ${error.message}</p>
                <p><strong>Stack:</strong> <pre>${error.stack || 'No stack trace'}</pre></p>
                <p>Please try refreshing the page or check your connection.</p>
            </div>
        `;
        stopAutoRefresh();
    } finally {
        // Reset button state
        setStatusButtonLoading(false);
    }
}

// Display job status
function displayStatus(status) {
    console.log('🔍 ==> displayStatus ENTRY');
    console.log('🔍 ==> Input status object:', status);
    console.log('🔍 ==> typeof status:', typeof status);
    console.log('🔍 ==> status.progress:', status.progress);
    console.log('🔍 ==> typeof status.progress:', typeof status.progress);
    
    const statusDiv = statusResult;
    
    try {
        // Update pipeline steps if in loading overlay
        if (status.status === 'processing') {
            console.log('🔍 ==> Status is processing, updating pipeline...');
            const currentStep = getCurrentStep(status.progress);
            console.log('🔍 ==> Current step:', currentStep);
            updatePipelineStep(currentStep);
        }
        
        console.log('🔍 ==> Processing progress entries...');
        const progressEntries = Object.entries(status.progress || {});
        console.log('🔍 ==> Progress entries:', progressEntries);
        
        const progressItems = progressEntries.map(([key, value], index) => {
            console.log(`🔍 ==> Progress item ${index}: key="${key}", value=`, value);
            console.log(`🔍 ==> Value type: ${typeof value}`);
            console.log(`🔍 ==> Value constructor: ${value?.constructor?.name || 'undefined'}`);
            
            try {
                const emoji = getProgressEmoji(key);
                console.log(`🔍 ==> Emoji for ${key}:`, emoji);
                
                const label = formatProgressLabel(key);
                console.log(`🔍 ==> Label for ${key}:`, label);
                
                const statusClass = getProgressStatusClass(value);
                console.log(`🔍 ==> Status class for ${key}:`, statusClass);
                
                // ULTRA-SAFE value handling with detailed debugging
                let valueStr = 'UNKNOWN';
                console.log(`🔍 ==> Processing value for ${key}...`);
                
                if (value === null) {
                    console.log(`🔍 ==> Value is null`);
                    valueStr = 'NULL';
                } else if (value === undefined) {
                    console.log(`🔍 ==> Value is undefined`);
                    valueStr = 'UNDEFINED';
                } else if (typeof value === 'string') {
                    console.log(`🔍 ==> Value is string: "${value}"`);
                    if (value.toUpperCase) {
                        valueStr = value.toUpperCase();
                        console.log(`🔍 ==> String converted to uppercase: "${valueStr}"`);
                    } else {
                        console.log(`🔍 ==> String has no toUpperCase method!`);
                        valueStr = String(value).toUpperCase();
                    }
                } else if (typeof value === 'object') {
                    console.log(`🔍 ==> Value is object:`, value);
                    const objValue = value.status || value.state || JSON.stringify(value);
                    console.log(`🔍 ==> Extracted object value:`, objValue);
                    
                    if (objValue && objValue.toString) {
                        valueStr = objValue.toString().toUpperCase();
                        console.log(`🔍 ==> Object value converted: "${valueStr}"`);
                    } else {
                        valueStr = 'OBJECT_ERROR';
                        console.log(`🔍 ==> Object value has no toString method`);
                    }
                } else if (typeof value === 'number') {
                    console.log(`🔍 ==> Value is number: ${value}`);
                    valueStr = value.toString().toUpperCase();
                } else if (typeof value === 'boolean') {
                    console.log(`🔍 ==> Value is boolean: ${value}`);
                    valueStr = value.toString().toUpperCase();
                } else {
                    console.log(`🔍 ==> Value is unknown type: ${typeof value}`);
                    valueStr = String(value).toUpperCase();
                }
                
                console.log(`🔍 ==> Final valueStr for ${key}: "${valueStr}"`);
                
                const listItem = `<li><span>${emoji} ${label}:</span> <strong class="${statusClass}">${valueStr}</strong></li>`;
                console.log(`🔍 ==> Generated list item for ${key}:`, listItem);
                
                return listItem;
                
            } catch (itemError) {
                console.error(`🔍 ==> ERROR processing item ${key}:`, itemError);
                console.error(`🔍 ==> Error stack:`, itemError.stack);
                return `<li><span>⚠️ ${key}:</span> <strong class="status-failed">ERROR: ${itemError.message}</strong></li>`;
            }
        });
        
        console.log('🔍 ==> All progress items processed:', progressItems);
        const progressItemsJoined = progressItems.join('');
        console.log('🔍 ==> Joined progress items:', progressItemsJoined);

        const finalHTML = `
            <div class="status ${status.status}">
                <h4>${getStatusEmoji(status.status)} Status: ${status.status.toUpperCase()}</h4>
                <p><strong>Last Updated:</strong> ${formatDateTime(status.updated_at)}</p>
                <p><strong>Progress:</strong></p>
                <ul class="progress-list">${progressItemsJoined}</ul>
                ${status.error ? `<p style="color: #dc3545; margin-top: 15px;"><strong>❌ Error:</strong> ${status.error}</p>` : ''}
                ${status.status === 'processing' ? '<p class="auto-refresh">🔄 Auto-refreshing every 3 seconds...</p>' : ''}
            </div>
        `;
        
        console.log('🔍 ==> Final HTML to be inserted:', finalHTML);
        statusDiv.innerHTML = finalHTML;
        console.log('🔍 ==> HTML inserted successfully');

        // Display results if completed
        if (status.status === 'completed' && status.result) {
            console.log('🔍 ==> Displaying results for completed job:', status.result);
            
            if (status.result.generated_images) {
                console.log('🔍 ==> Calling displayImages...');
                displayImages(status.result.generated_images);
            }
            if (status.result.models_3d) {
                console.log('🔍 ==> Calling displayModels...');
                displayModels(status.result.models_3d);
            }
            if (status.result.blender_result) {
                console.log('🔍 ==> Calling displayFinalFiles...');
                displayFinalFiles(status.result.blender_result);
            }
            if (status.result.final_package) {
                console.log('🔍 ==> Calling displayPackage...');
                displayPackage(status.result.final_package);
            }
        }
        
        console.log('🔍 ==> displayStatus completed successfully');
        
    } catch (error) {
        console.error('🔍 ==> FATAL ERROR in displayStatus:', error);
        console.error('🔍 ==> Error name:', error.name);
        console.error('🔍 ==> Error message:', error.message);
        console.error('🔍 ==> Error stack:', error.stack);
        console.error('🔍 ==> Input status was:', status);
        
        statusDiv.innerHTML = `
            <div class="status failed">
                <h4>❌ Display Error</h4>
                <p><strong>Error:</strong> ${error.message}</p>
                <p><strong>Error Type:</strong> ${error.name}</p>
                <p><strong>Stack:</strong> <pre>${error.stack}</pre></p>
                <p><strong>Raw status data:</strong> <pre>${JSON.stringify(status, null, 2)}</pre></p>
            </div>
        `;
    }
    
    console.log('🔍 ==> displayStatus EXIT');
}

// Display generated images
function displayImages(images) {
    if (!images || images.length === 0) {
        imagesContainer.innerHTML = '<p>No images generated.</p>';
        return;
    }
    
    let imagesHtml = `<h3>🎨 Generated Images (${images.length})</h3><div class="images-grid">`;
    
    images.forEach((img, index) => {
        const imageUrl = `${API_BASE}${img.url}`;
        const methodBadge = img.method ? img.method.replace('_', ' ').toUpperCase() : 'AI GENERATED';
        const typeTitle = formatImageType(img.type);
        
        imagesHtml += `
            <div class="image-card">
                <div class="method-badge ${img.method || 'ai_generated'}">${methodBadge}</div>
                <h4>${typeTitle}</h4>
                <img src="${imageUrl}" 
                     alt="${img.type}" 
                     loading="lazy" 
                     onerror="handleImageError(this)">
                <div class="image-details">
                    <strong>File:</strong> ${img.filename}<br>
                    <strong>Size:</strong> ${img.size || '1024x1536'}<br>
                    <strong>Generated:</strong> ${formatDateTime(img.generated_at)}
                    ${img.tokens_used ? `<br><strong>Tokens Used:</strong> ${img.tokens_used}` : ''}
                </div>
                <a href="${imageUrl}" target="_blank" class="download-link">📥 View Full Size</a>
            </div>
        `;
    });
    
    imagesHtml += '</div>';
    imagesContainer.innerHTML = imagesHtml;
}

// Utility Functions
function validateForm() {
    const userImage = document.getElementById('userImage').files[0];
    const style = document.getElementById('style').value;
    const accessory1 = document.getElementById('accessory1').value.trim();
    const accessory2 = document.getElementById('accessory2').value.trim();
    const accessory3 = document.getElementById('accessory3').value.trim();
    
    if (!userImage) {
        showNotification('📸 Please select an image file', 'error');
        return false;
    }
    
    // Check file size (50MB limit)
    if (userImage.size > 50 * 1024 * 1024) {
        showNotification('📏 Image file is too large. Maximum size is 50MB.', 'error');
        return false;
    }
    
    // Check file type
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
    if (!allowedTypes.includes(userImage.type)) {
        showNotification('🖼️ Please select a valid image file (JPG, PNG, WEBP)', 'error');
        return false;
    }
    
    if (!style) {
        showNotification('🎨 Please select a style theme', 'error');
        return false;
    }
    
    if (!accessory1 || !accessory2 || !accessory3) {
        showNotification('⚔️ Please fill in all accessory fields', 'error');
        return false;
    }
    
    return true;
}

function setSubmitButtonLoading(loading) {
    submitBtn.disabled = loading;
    submitText.style.display = loading ? 'none' : 'inline';
    submitLoading.style.display = loading ? 'inline-block' : 'none';
}

function setStatusButtonLoading(loading) {
    statusBtn.disabled = loading;
    statusText.style.display = loading ? 'none' : 'inline';
    statusLoading.style.display = loading ? 'inline-block' : 'none';
}

function stopAutoRefresh() {
    if (statusInterval) {
        clearInterval(statusInterval);
        statusInterval = null;
    }
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        border-radius: 8px;
        color: white;
        font-weight: 600;
        z-index: 1000;
        max-width: 400px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        animation: slideIn 0.3s ease-out;
    `;
    
    // Set background color based on type
    const colors = {
        success: '#28a745',
        error: '#dc3545',
        info: '#17a2b8',
        warning: '#ffc107'
    };
    notification.style.backgroundColor = colors[type] || colors.info;
    notification.textContent = message;
    
    // Add to page
    document.body.appendChild(notification);
    
    // Remove after 5 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 5000);
}

function getProgressEmoji(key) {
    const emojis = {
        upload: '📤',
        ai_generation: '🤖',
        image_processing: '🖼️',
        '3d_conversion': '🎯',
        blender_processing: '🎨',
        style_application: '✨',
        background_removal: '🔍',
        character_enhancement: '👤'
    };
    return emojis[key] || '⚙️';
}

function formatProgressLabel(key) {
    const labels = {
        upload: 'Upload',
        ai_generation: 'AI Generation',
        image_processing: 'Image Processing',
        '3d_conversion': '3D Conversion',
        blender_processing: 'Blender Processing',
        style_application: 'Style Application',
        background_removal: 'Background Removal',
        character_enhancement: 'Character Enhancement'
    };
    return labels[key] || key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function getProgressStatusClass(status) {
    console.log('🔍 getProgressStatusClass input:', status, typeof status);
    
    let statusValue = 'unknown';
    
    try {
        if (status !== null && status !== undefined) {
            if (typeof status === 'object') {
                statusValue = status.status || status.state || 'unknown';
                console.log('🔍 Extracted from object:', statusValue);
            } else {
                statusValue = String(status);
                console.log('🔍 Converted to string:', statusValue);
            }
        }
        
        if (statusValue && statusValue.toString) {
            statusValue = statusValue.toString().toLowerCase();
            console.log('🔍 Final statusValue:', statusValue);
        } else {
            console.log('🔍 StatusValue has no toString method:', statusValue);
            statusValue = 'unknown';
        }
        
        const classes = {
            pending: 'status-pending',
            processing: 'status-processing', 
            in_progress: 'status-processing',
            running: 'status-processing',
            completed: 'status-completed',
            success: 'status-completed',
            done: 'status-completed',
            failed: 'status-failed',
            error: 'status-failed'
        };
        
        const result = classes[statusValue] || 'status-pending';
        console.log('🔍 getProgressStatusClass result:', result);
        return result;
        
    } catch (error) {
        console.error('🔍 ERROR in getProgressStatusClass:', error);
        return 'status-failed';
    }
}

function getStatusEmoji(status) {
    const emojis = {
        queued: '⏳',
        processing: '🔄',
        completed: '✅',
        failed: '❌'
    };
    return emojis[status] || '📋';
}

function formatImageType(type) {
    return type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function formatDateTime(dateString) {
    return new Date(dateString).toLocaleString();
}

function handleImageError(img) {
    img.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZjhmOWZhIiBzdHJva2U9IiNkZWUyZTYiIHN0cm9rZS13aWR0aD0iMiIvPjx0ZXh0IHg9IjUwJSIgeT0iNDAlIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTQiIGZpbGw9IiM2Yzc1N2QiIHRleHQtYW5jaG9yPSJtaWRkbGUiPkltYWdlIE5vdCBGb3VuZDwvdGV4dD48dGV4dCB4PSI1MCUiIHk9IjYwJSIgZm9udC1mYW1pbHk9IkFyaWFsIiBmb250LXNpemU9IjEyIiBmaWxsPSIjOTk5IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj5DbGljayB0byByZXRyeTwvdGV4dD48L3N2Zz4=';
    img.alt = 'Image not found';
    img.style.cursor = 'pointer';
    img.onclick = () => location.reload();
}

// Add these new functions to your existing script.js

// NEW: Display 3D models
function displayModels(models) {
    if (!models || models.length === 0) return;
    
    const modelsContainer = document.getElementById('modelsContainer');
    const modelsList = document.getElementById('modelsList');
    
    let modelsHtml = '<div class="models-grid">';
    
    models.forEach(model => {
        const modelUrl = `${API_BASE}${model.url}`;
        modelsHtml += `
            <div class="model-card">
                <h4>${model.name}</h4>
                <div class="model-info">
                    <strong>Type:</strong> ${model.type}<br>
                    <strong>File:</strong> ${model.filename}
                </div>
                <a href="${modelUrl}" download class="download-link">📥 Download ${model.type.toUpperCase()}</a>
            </div>
        `;
    });
    
    modelsHtml += '</div>';
    modelsList.innerHTML = modelsHtml;
    modelsContainer.style.display = 'block';
}

// NEW: Display final package
function displayPackage(packageData) {
    if (!packageData) return;
    
    const packageContainer = document.getElementById('packageContainer');
    const packageDownloads = document.getElementById('packageDownloads');
    
    const packageUrl = `${API_BASE}${packageData.url}`;
    
    packageDownloads.innerHTML = `
        <div class="package-card">
            <h4>🎁 Complete Starter Pack</h4>
            <p>Contains all images, 3D models, and assembly files</p>
            <div class="package-info">
                <strong>File:</strong> ${packageData.filename}<br>
                <strong>Size:</strong> ${packageData.size || 'Unknown'}<br>
                <strong>Items:</strong> ${packageData.item_count || 'Multiple'} files
            </div>
            <a href="${packageUrl}" download class="download-link package-download">
                📦 Download Complete Package
            </a>
        </div>
    `;
    
    packageContainer.style.display = 'block';
}

// NEW: Update pipeline steps visual
function updatePipelineStep(currentStep) {
    const steps = document.querySelectorAll('.pipeline-steps .step');
    
    steps.forEach(step => {
        const stepName = step.dataset.step;
        step.classList.remove('active', 'completed');
        
        if (stepName === currentStep) {
            step.classList.add('active');
        } else {
            // Mark previous steps as completed
            const stepOrder = ['upload', 'ai_generation', 'background_removal', '3d_conversion', 'blender_processing'];
            const currentIndex = stepOrder.indexOf(currentStep);
            const stepIndex = stepOrder.indexOf(stepName);
            
            if (stepIndex < currentIndex) {
                step.classList.add('completed');
            }
        }
    });
}

// NEW: Get current pipeline step
function getCurrentStep(progress) {
    const stepOrder = ['upload', 'ai_generation', 'background_removal', '3d_conversion', 'blender_processing'];
    
    for (let i = stepOrder.length - 1; i >= 0; i--) {
        const step = stepOrder[i];
        if (progress[step] === 'processing') {
            return step;
        }
    }
    
    // Return the last completed step
    for (let i = stepOrder.length - 1; i >= 0; i--) {
        const step = stepOrder[i];
        if (progress[step] === 'completed') {
            return step;
        }
    }
    
    return 'upload';
}

// UPDATED: Add new progress emojis
function getProgressEmoji(key) {
    const emojis = {
        upload: '📤',
        ai_generation: '🤖',
        image_processing: '🖼️',
        background_removal: '🔍',
        '3d_conversion': '🎯',
        blender_processing: '🎨',
        style_application: '✨',
        character_enhancement: '👤'
    };
    return emojis[key] || '⚙️';
}

// Modal event listeners
document.addEventListener('DOMContentLoaded', function() {
    // Close modal when clicking the X
    const closeBtn = document.querySelector('.close');
    if (closeBtn) {
        closeBtn.onclick = closeStyleModal;
    }
    
    // Close modal when clicking outside
    window.onclick = function(event) {
        const modal = document.getElementById('styleModal');
        if (event.target === modal) {
            closeStyleModal();
        }
    };
    
    // Close modal with Escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            closeStyleModal();
            hideLoadingOverlay();
        }
    });
});

// File input preview
document.getElementById('userImage').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (file) {
        // Show file info
        const fileInfo = document.createElement('div');
        fileInfo.className = 'file-info';
        fileInfo.innerHTML = `
            <small style="color: #28a745; font-weight: 600;">
                ✅ Selected: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)
            </small>
        `;
        
        // Remove existing file info
        const existingInfo = document.querySelector('.file-info');
        if (existingInfo) {
            existingInfo.remove();
        }
        
        // Add new file info
        e.target.parentNode.appendChild(fileInfo);
        
        // Validate file immediately
        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
        if (!allowedTypes.includes(file.type)) {
            showNotification('⚠️ Please select a valid image file (JPG, PNG, WEBP)', 'warning');
        } else if (file.size > 50 * 1024 * 1024) {
            showNotification('⚠️ File is too large. Maximum size is 50MB.', 'warning');
        } else {
            showNotification('✅ Image file looks good!', 'success');
        }
    }
});

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
    
    .status-pending { color: #ffc107; }
    .status-processing { color: #17a2b8; }
    .status-completed { color: #28a745; }
    .status-failed { color: #dc3545; }
    
    .file-info {
        margin-top: 8px;
        animation: slideIn 0.3s ease-out;
    }
    
    .notification {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        border-left: 4px solid rgba(255,255,255,0.3);
    }
    
    .form-group.enhanced {
        position: relative;
        transition: all 0.3s ease;
    }
    
    .form-group.enhanced:focus-within {
        transform: translateY(-2px);
    }
`;
document.head.appendChild(style);

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopAutoRefresh();
});

// Auto-save form data to localStorage
function saveFormData() {
    const formData = {
        style: document.getElementById('style').value,
        accessory1: document.getElementById('accessory1').value,
        accessory2: document.getElementById('accessory2').value,
        accessory3: document.getElementById('accessory3').value
    };
    localStorage.setItem('characterGeneratorForm', JSON.stringify(formData));
}

// Load form data from localStorage
function loadFormData() {
    const savedData = localStorage.getItem('characterGeneratorForm');
    if (savedData) {
        try {
            const formData = JSON.parse(savedData);
            if (formData.style) document.getElementById('style').value = formData.style;
            if (formData.accessory1) document.getElementById('accessory1').value = formData.accessory1;
            if (formData.accessory2) document.getElementById('accessory2').value = formData.accessory2;
            if (formData.accessory3) document.getElementById('accessory3').value = formData.accessory3;
            
            // Trigger style change event if style was loaded
            if (formData.style) {
                styleSelect.dispatchEvent(new Event('change'));
            }
        } catch (error) {
            console.error('Error loading saved form data:', error);
        }
    }
}

// Save form data when inputs change
document.addEventListener('DOMContentLoaded', function() {
    loadFormData();
    
    // Auto-save on input changes
    ['style', 'accessory1', 'accessory2', 'accessory3'].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('input', saveFormData);
            element.addEventListener('change', saveFormData);
        }
    });
});

// STL Viewer Variables
let stlScene, stlCamera, stlRenderer, stlControls, stlModel;
let isWireframe = false;
let autoRotate = false;

// Initialize STL Viewer
function initSTLViewer() {
    const container = document.getElementById('stlViewer');
    if (!container) return;

    // Scene setup
    stlScene = new THREE.Scene();
    stlScene.background = new THREE.Color(0xf8f9fa);

    // Camera setup
    stlCamera = new THREE.PerspectiveCamera(75, container.clientWidth / container.clientHeight, 0.1, 1000);
    stlCamera.position.set(0, 0, 100);

    // Renderer setup
    stlRenderer = new THREE.WebGLRenderer({ antialias: true });
    stlRenderer.setSize(container.clientWidth, container.clientHeight);
    stlRenderer.shadowMap.enabled = true;
    stlRenderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(stlRenderer.domElement);

    // Controls setup
    stlControls = new THREE.OrbitControls(stlCamera, stlRenderer.domElement);
    stlControls.enableDamping = true;
    stlControls.dampingFactor = 0.05;
    stlControls.autoRotate = false;
    stlControls.autoRotateSpeed = 2.0;

    // Lighting setup
    const ambientLight = new THREE.AmbientLight(0x404040, 0.6);
    stlScene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(50, 50, 50);
    directionalLight.castShadow = true;
    directionalLight.shadow.mapSize.width = 2048;
    directionalLight.shadow.mapSize.height = 2048;
    stlScene.add(directionalLight);

    const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.4);
    directionalLight2.position.set(-50, -50, -50);
    stlScene.add(directionalLight2);

    // Start render loop
    animateSTLViewer();

    // Handle window resize
    window.addEventListener('resize', onSTLViewerResize);
}

// STL Viewer animation loop
function animateSTLViewer() {
    requestAnimationFrame(animateSTLViewer);
    
    if (stlControls) {
        stlControls.update();
    }
    
    if (stlRenderer && stlScene && stlCamera) {
        stlRenderer.render(stlScene, stlCamera);
    }
}

// Handle STL viewer resize
function onSTLViewerResize() {
    const container = document.getElementById('stlViewer');
    if (!container || !stlCamera || !stlRenderer) return;

    stlCamera.aspect = container.clientWidth / container.clientHeight;
    stlCamera.updateProjectionMatrix();
    stlRenderer.setSize(container.clientWidth, container.clientHeight);
}

// Load STL file into viewer
function loadSTLFile(url) {
    if (!stlScene) {
        initSTLViewer();
    }

    const container = document.getElementById('stlViewer');
    container.classList.add('loading');

    // Remove existing model
    if (stlModel) {
        stlScene.remove(stlModel);
    }

    // Load STL
    const loader = new THREE.STLLoader();
    loader.load(
        url,
        function (geometry) {
            // Create material
            const material = new THREE.MeshPhongMaterial({
                color: 0x667eea,
                shininess: 100,
                transparent: true,
                opacity: 0.9
            });

            // Create mesh
            stlModel = new THREE.Mesh(geometry, material);
            stlModel.castShadow = true;
            stlModel.receiveShadow = true;

            // Center and scale the model
            const box = new THREE.Box3().setFromObject(stlModel);
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            
            // Center the model
            stlModel.position.sub(center);
            
            // Scale to fit in view
            const maxDim = Math.max(size.x, size.y, size.z);
            const scale = 50 / maxDim;
            stlModel.scale.setScalar(scale);

            stlScene.add(stlModel);
            container.classList.remove('loading');

            // Reset camera position
            resetSTLView();

            console.log('STL loaded successfully');
        },
        function (progress) {
            console.log('Loading progress:', (progress.loaded / progress.total * 100) + '%');
        },
        function (error) {
            console.error('Error loading STL:', error);
            container.classList.remove('loading');
            showNotification('❌ Error loading 3D model', 'error');
        }
    );
}

// Reset STL viewer camera
function resetSTLView() {
    if (!stlCamera || !stlControls) return;
    
    stlCamera.position.set(0, 0, 100);
    stlControls.reset();
}

// Toggle wireframe mode
function toggleWireframe() {
    if (!stlModel) return;
    
    isWireframe = !isWireframe;
    stlModel.material.wireframe = isWireframe;
    
    const btn = document.querySelector('.viewer-btn[onclick="toggleWireframe()"]');
    if (btn) {
        btn.textContent = isWireframe ? '🎨 Solid' : '📐 Wireframe';
    }
}

// Toggle auto rotate
function toggleAutoRotate() {
    if (!stlControls) return;
    
    autoRotate = !autoRotate;
    stlControls.autoRotate = autoRotate;
    
    const btn = document.querySelector('.viewer-btn[onclick="toggleAutoRotate()"]');
    if (btn) {
        btn.textContent = autoRotate ? '⏸️ Stop Rotate' : '🔄 Auto Rotate';
    }
}

// Display final files
function displayFinalFiles(blenderResult) {
    if (!blenderResult || !blenderResult.output_files || blenderResult.output_files.length === 0) {
        return;
    }

    const container = document.getElementById('finalFilesContainer');
    const filesList = document.getElementById('finalFilesList');
    
    let filesHtml = '';
    
    blenderResult.output_files.forEach(file => {
        const fileExtension = file.file_extension || '.unknown';
        const isSTL = fileExtension.toLowerCase() === '.stl';
        const isBlend = fileExtension.toLowerCase() === '.blend';
        
        const fileTypeClass = isSTL ? 'stl' : isBlend ? 'blend' : 'unknown';
        const fileIcon = isSTL ? '🎯' : isBlend ? '🎨' : '📄';
        const fileTypeName = isSTL ? 'STL' : isBlend ? 'Blender' : 'File';
        
        filesHtml += `
            <div class="final-file-card">
                <h4>
                    ${fileIcon} ${file.filename}
                    <span class="file-type-badge ${fileTypeClass}">${fileTypeName}</span>
                </h4>
                <div class="file-info">
                    <strong>Size:</strong> ${file.file_size_mb} MB<br>
                    <strong>Created:</strong> ${formatDateTime(file.created_at)}<br>
                    <strong>Type:</strong> ${fileTypeName} File
                </div>
                <div class="file-actions">
                    <a href="${API_BASE}${file.download_url}"
                       download="${file.filename}"
                       class="download-btn">
                        📥 Download ${fileTypeName}
                    </a>
                    ${isSTL ? `
                        <button onclick="viewSTLFile('${API_BASE}${file.download_url}', '${file.filename}')"
                                class="view-btn">
                            👁️ View 3D
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    });
    
    filesList.innerHTML = filesHtml;
    container.style.display = 'block';
}

// View STL file in 3D viewer
function viewSTLFile(url, filename) {
    const viewerContainer = document.getElementById('stlViewerContainer');
    viewerContainer.style.display = 'block';
    
    // Scroll to viewer
    viewerContainer.scrollIntoView({ behavior: 'smooth' });
    
    // Update viewer title
    const title = viewerContainer.querySelector('h3');
    title.textContent = `🎯 3D Model Viewer - ${filename}`;
    
    // Load the STL file
    loadSTLFile(url);
    
    showNotification('🎯 Loading 3D model...', 'info');
}

// Export functions for global access
window.showStyleModal = showStyleModal;
window.closeStyleModal = closeStyleModal;
window.resetSTLView = resetSTLView;
window.toggleWireframe = toggleWireframe;
window.toggleAutoRotate = toggleAutoRotate;
window.viewSTLFile = viewSTLFile;
