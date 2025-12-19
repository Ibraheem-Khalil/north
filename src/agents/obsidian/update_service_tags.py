"""
Auto-update service tags from Weaviate database
Run this after ingestion to keep tags synchronized
"""

import json
import weaviate
from datetime import datetime
from pathlib import Path

def update_service_tags():
    """Extract all unique service tags from Weaviate and save to JSON"""
    
    client = weaviate.connect_to_local()
    
    try:
        company = client.collections.get('Company')
        
        # Get ALL companies to extract unique services
        all_companies = company.query.fetch_objects(limit=1000)
        
        # Extract all unique services
        all_services = set()
        for obj in all_companies.objects:
            services = obj.properties.get('services', [])
            if services:
                if isinstance(services, list):
                    all_services.update(services)
                else:
                    all_services.add(services)
        
        # Sort for consistency
        unique_services = sorted(list(all_services))
        
        # Save to JSON
        tags_file = Path(__file__).parent / 'service_tags.json'
        tags_data = {
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_count": len(unique_services),
            "services": unique_services
        }
        
        with open(tags_file, 'w') as f:
            json.dump(tags_data, f, indent=2)
        
        print(f"✓ Updated service tags: {len(unique_services)} unique services")
        print(f"✓ Saved to: {tags_file}")
        
        return unique_services
        
    finally:
        client.close()

if __name__ == "__main__":
    update_service_tags()